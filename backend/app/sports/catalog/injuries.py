"""Injuries, their phases, the measures that place an athlete in a phase,
and the criteria that clear them to the next one and back to sport.

The rules are criteria-based, not time-based: an athlete leaves a phase
when the measures say so, with the calendar as a floor (an ACL graft is not
ready for cutting at twelve weeks whatever the hop test says). Cut-offs are
the published ones:

* ACL: the Delaware–Oslo / MOON return-to-sport criteria (quadriceps LSI
  ≥ 90%, hop battery LSI ≥ 90%, ≥ 9 months from surgery — Grindem et al.
  2016 BJSM: each month of delay to nine reduced reinjury 51%), the
  Melbourne ACL Rehabilitation Guide phases, ACL-RSI ≥ 65 (Webster 2018),
  IKDC ≥ 85, effusion by the stroke test (Sturgill 2009), the pain-
  monitoring model (≤ 3/10 during, settled by next morning).
* Ankle: the 2019 ROAST consensus and Doherty 2017 (CAIT ≥ 24, FAAM
  Sport ≥ 90%, dorsiflexion within 2 cm, hop LSI ≥ 90%).
* Patellar tendon: VISA-P (Visentini 1998), the Malliaras 2015 progression.
* Hamstring: BAMIC grading, the Askling H-test, Nordic strength (Opar 2015),
  the control–chaos continuum for running.
* Groin: the Doha agreement (2015), HAGOS, adductor squeeze.
* Concussion: SCAT6 / the 2022 Amsterdam consensus stepwise return.

Nothing here clears anyone: the app shows the criteria met and unmet and
the medical staff make the call. The guardrail sentence says so on every
rehab screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MeasureSpec:
    key: str
    label: str
    unit: str
    higher_is_better: bool
    protocol: str
    why: str
    # sided: recorded for the involved and uninvolved limb, so an LSI exists
    sided: bool = False
    kind: str = "number"      # number | grade | score | yes_no
    lo: float | None = None
    hi: float | None = None
    decimals: int = 0
    phone: bool = False
    devices: tuple[str, ...] = ("manual",)
    symbol: str = "ruler"
    # The matching performance-test key, when the measure is the same thing
    # (so a test logged on the Stats tab counts here too).
    test_key: str | None = None
    # Minimal detectable change in the measure's unit: a move smaller than
    # this is measurement noise and the app says so rather than celebrating it.
    mdc: float | None = None


MEASURES: dict[str, MeasureSpec] = {}


def _m(spec: MeasureSpec) -> None:
    MEASURES[spec.key] = spec


# --- knee -------------------------------------------------------------------------------------

_m(MeasureSpec("knee_flexion", "Knee flexion", "°", True,
               "Supine or prone, heel toward the buttock; the phone on the shin as an inclinometer "
               "or a goniometer. Both knees.",
               "Range comes back in a known order. Full flexion (within 10° of the other knee) "
               "is a late-phase gate. Phone inclinometer apps measure the knee within 1–3°, so stay on "
               "one device.", sided=True, lo=0, hi=160, phone=True,
               devices=("phone", "goniometer"), symbol="angle", mdc=5))
_m(MeasureSpec("knee_extension_deficit", "Knee extension deficit", "°", False,
               "Supine, heel propped; degrees short of the other knee's full extension "
               "(hyperextension counts as negative).",
               "Full extension is the first goal of every knee rehab. A 3–5° deficit at six "
               "weeks predicts a worse outcome; it must be 0 to run.", sided=False, lo=-10, hi=45,
               phone=True, devices=("phone", "goniometer"), symbol="angle"))
_m(MeasureSpec("effusion_grade", "Effusion (stroke test)", "grade", False,
               "Stroke the medial knee upward three times, then downward on the lateral side; "
               "grade 0 (none), trace, 1+ (small wave), 2+ (returns without stroke), 3+ (tense).",
               "Swelling is the knee saying no. Trace or less is required to progress loading; "
               "1+ or worse after a session means the session was too much.", kind="grade",
               lo=0, hi=3, symbol="drop.fill"))
_m(MeasureSpec("quad_strength", "Quadriceps strength", "N", True,
               "Seated isometric knee extension at 60–90° on a dynamometer, peak of three. Both legs.",
               "The single strongest predictor of knee function after ACL surgery. The LSI "
               "(involved over uninvolved) gates jogging at 70%, running and cutting at 80%, "
               "return to sport at 90%.", sided=True, lo=0, hi=1500, devices=("dynamometer", "isokinetic"),
               symbol="dumbbell.fill", test_key="knee_extension_iso"))
_m(MeasureSpec("hamstring_strength", "Hamstring strength", "N", True,
               "Prone or seated isometric knee flexion at 30° on a dynamometer. Both legs.",
               "Graft donor site for a hamstring autograft, and the knee's dynamic protector; "
               "H:Q ratio ≥ 0.6.", sided=True, lo=0, hi=800, devices=("dynamometer",),
               symbol="dumbbell.fill", test_key="knee_flexion_iso"))
_m(MeasureSpec("hop_single", "Single hop for distance", "cm", True,
               "One-leg hop forward, land and hold two seconds. Best of three per leg.",
               "First of the hop battery; LSI ≥ 90% on all four is the return-to-sport standard.",
               sided=True, lo=0, hi=300, symbol="figure.jumprope", test_key="hop_single_distance"))
_m(MeasureSpec("hop_triple", "Triple hop for distance", "cm", True,
               "Three consecutive one-leg hops forward, total distance. Best of three per leg.",
               "Power and control over repeated landings.", sided=True, lo=0, hi=900,
               symbol="figure.jumprope"))
_m(MeasureSpec("hop_crossover", "Crossover hop for distance", "cm", True,
               "Three one-leg hops crossing a line each time, total distance. Best of three per leg.",
               "Adds the frontal-plane control a cut demands.", sided=True, lo=0, hi=900,
               symbol="figure.jumprope"))
_m(MeasureSpec("hop_timed_6m", "6 m timed hop", "s", False,
               "One-leg hops over six metres as fast as possible; the phone's stopwatch or gates.",
               "Speed on one leg. Lower is better, so the LSI is uninvolved over involved.",
               sided=True, lo=0, hi=10, decimals=2, phone=True, devices=("phone", "timing_gates"),
               symbol="timer"))
_m(MeasureSpec("single_leg_cmj", "Single-leg jump height", "cm", True,
               "One-leg countermovement jump, hands on hips, force plate or the phone's flight-time test.",
               "The force-plate version of the hop: height and, on a plate, how the landing is "
               "absorbed.", sided=True, lo=0, hi=50, decimals=1, phone=True,
               devices=("force_plate", "phone"), symbol="figure.jumprope", test_key="single_leg_cmj"))
_m(MeasureSpec("slr_lag", "Straight-leg raise lag", "°", False,
               "Supine, lift the straight leg; degrees of knee bend that appear on the way up.",
               "Quad activation. Zero lag before weight-bearing progresses.", lo=0, hi=30,
               symbol="figure.walk"))
_m(MeasureSpec("y_balance_anterior_diff", "Y-balance anterior difference", "cm", False,
               "Anterior reach of the Y-balance test; the difference between legs.",
               "More than 4 cm between legs is a knee-injury risk marker.", lo=0, hi=20,
               decimals=1, symbol="figure.stand"))
_m(MeasureSpec("acl_rsi", "ACL-RSI", "/100", True,
               "The 12-item ACL Return to Sport after Injury scale (or the 6-item short form), scored 0–100.",
               "Psychological readiness. 65 is the validated gate for returning to the prior level "
               "(Sadeqi 2018); a low score at 9–12 months doubles graft-rupture odds. It is the "
               "criterion most programs forget. Re-take it every four weeks.",
               kind="score", lo=0, hi=100, symbol="brain.head.profile"))
_m(MeasureSpec("ikdc", "IKDC subjective", "/100", True,
               "The IKDC subjective knee form, 18 items, scored 0–100.",
               "Knee function in the athlete's own words; 75.9 is the patient-acceptable state after ACL "
               "surgery and 85–90 is where athletes return.", kind="score",
               lo=0, hi=100, symbol="doc.text", mdc=11.5))
_m(MeasureSpec("koos_sport", "KOOS sport & recreation", "/100", True,
               "The KOOS sport/recreation subscale, scored 0–100.",
               "Function in sport-specific tasks; 75 is the acceptable state after ACL surgery.",
               kind="score", lo=0, hi=100, symbol="doc.text", mdc=5.8))
_m(MeasureSpec("tampa_tsk", "Kinesiophobia (TSK-11)", "/44", False,
               "The 11-item Tampa Scale, 11–44.",
               "Fear of movement. The Melbourne guide's hurdle: 11–18 passes, 19 or more fails and "
               "is worth addressing before cutting work.",
               kind="score", lo=11, hi=44, symbol="brain.head.profile"))
_m(MeasureSpec("lysholm", "Lysholm", "/100", True, "The Lysholm knee score.", "Symptoms in daily life.",
               kind="score", lo=0, hi=100, symbol="doc.text"))
_m(MeasureSpec("visa_p", "VISA-P", "/100", True,
               "The Victorian Institute of Sport Assessment, patellar tendon, 8 items, 0–100.",
               "Patellar tendon function; under 80 is symptomatic, above 90 is where most return. A change "
               "under 13 points is noise; re-test every four weeks, not every week.",
               kind="score", lo=0, hi=100, symbol="doc.text", mdc=13))
_m(MeasureSpec("decline_squat_pain", "Single-leg decline squat pain", "/10", False,
               "Single-leg squat on a 25° decline board to about 60°; pain 0–10 on the involved side.",
               "The tendon's own load test. The pain-monitoring model: 0–2 safe, 3–5 acceptable, "
               "6–10 too much; and settled by the next morning.", lo=0, hi=10, symbol="bandage.fill"))
_m(MeasureSpec("kujala", "Kujala (AKPS)", "/100", True, "The anterior knee pain scale, 0–100.",
               "Patellofemoral function.", kind="score", lo=0, hi=100, symbol="doc.text"))
_m(MeasureSpec("knee_valgus_dvj", "Knee valgus on landing", "grade", False,
               "Drop vertical jump on video or markerless capture; valgus graded 0 (none) to 2 (marked).",
               "The landing pattern an ACL prevention programme fixes.", kind="grade", lo=0, hi=2,
               devices=("video", "phone"), symbol="video"))

# --- ankle & foot ----------------------------------------------------------------------------------

_m(MeasureSpec("ankle_dorsiflexion", "Ankle dorsiflexion (knee-to-wall)", "cm", True,
               "Knee to the wall with the heel down; the toe-to-wall distance where the knee still touches. Both sides.",
               "The first range a sprained ankle loses and the last it gets back. Within 2 cm of the other side to return.",
               sided=True, lo=0, hi=20, decimals=1, phone=True, devices=("phone", "manual"),
               symbol="ruler", test_key="ankle_dorsiflexion_ktw"))
_m(MeasureSpec("ankle_girth_figure8", "Ankle swelling (figure-of-8)", "cm", False,
               "Tape measure in a figure of eight around the malleoli and midfoot. Both sides.",
               "Swelling in a number; within 1 cm of the other ankle before hopping.", sided=True,
               lo=30, hi=80, decimals=1, symbol="drop.fill"))
_m(MeasureSpec("single_leg_balance_s", "Single-leg balance, eyes closed", "s", True,
               "Hands on hips, eyes closed, one leg; seconds to a touch-down, up to 60. Both legs.",
               "Proprioception, the thing a sprain damages most and the thing that prevents the next one. "
               "Nine seconds eyes closed is the published norm.",
               sided=True, lo=0, hi=60, phone=True, devices=("phone", "manual"), symbol="figure.stand",
               test_key="single_leg_balance"))
_m(MeasureSpec("sebt_composite", "Star excursion / Y-balance composite", "%", True,
               "Y-balance composite reach per leg as a percentage of leg length.",
               "Dynamic control; within 4 cm anterior reach between sides and composite ≥ 94%.",
               sided=True, lo=50, hi=130, decimals=1, symbol="figure.stand", test_key="y_balance_composite"))
_m(MeasureSpec("cait", "CAIT", "/30", True,
               "The Cumberland Ankle Instability Tool, 9 items, 0–30.",
               "Perceived instability; 25 or under defines chronic ankle instability (the recalibrated cut).",
               kind="score",
               lo=0, hi=30, symbol="doc.text"))
_m(MeasureSpec("faam_sport", "FAAM Sport", "%", True,
               "The Foot and Ankle Ability Measure, sport subscale, as a percentage.",
               "Sport function; under 80% defines chronic instability, ≥ 90% at return.", kind="score",
               lo=0, hi=100, symbol="doc.text", mdc=9))
_m(MeasureSpec("hop_lateral", "Side hop test", "s", False,
               "Ten lateral hops over a 30 cm gap on one leg, timed. Both legs.",
               "Frontal-plane ankle control; LSI ≥ 90% (uninvolved over involved).", sided=True,
               lo=0, hi=30, decimals=2, phone=True, symbol="timer"))
_m(MeasureSpec("visa_a", "VISA-A", "/100", True, "The VISA Achilles questionnaire, 0–100.",
               "Achilles tendon function.", kind="score", lo=0, hi=100, symbol="doc.text"))
_m(MeasureSpec("atrs", "ATRS", "/100", True, "The Achilles tendon Total Rupture Score.",
               "Function after rupture.", kind="score", lo=0, hi=100, symbol="doc.text"))
_m(MeasureSpec("calf_raise_reps", "Single-leg calf raises", "reps", True,
               "One-leg heel raises off a step to failure. Both legs.",
               "Calf endurance; LSI ≥ 90% and 25+ reps before running.", sided=True, lo=0, hi=60,
               symbol="figure.walk", test_key="calf_raise_reps"))

# --- hamstring, groin, hip, calf -------------------------------------------------------------------

_m(MeasureSpec("askling_h_pain", "Askling H-test", "/10", False,
               "Supine, kick the straight leg up fast three times; worst pain and insecurity 0–10.",
               "The hamstring's return-to-sprint gate: 0 out of 10 on the last day before return.",
               lo=0, hi=10, symbol="bandage.fill"))
_m(MeasureSpec("nordic_force", "Nordic hamstring force", "N", True,
               "Eccentric peak force on the NordBord per leg.",
               "Below 337 N or over 15% between legs raises re-strain risk.", sided=True, lo=0,
               hi=800, devices=("nordbord",), symbol="dumbbell.fill", test_key="nordic_hamstring_force"))
_m(MeasureSpec("hamstring_ake", "Active knee extension", "°", False,
               "Supine, hip at 90°, actively straighten; degrees short of full. Both legs.",
               "Hamstring length; within 10° of the other leg to sprint.", sided=True, lo=0, hi=60,
               phone=True, devices=("phone", "goniometer"), symbol="angle", test_key="hamstring_ake"))
_m(MeasureSpec("sprint_pct_max", "Sprint speed reached", "% of max", True,
               "The fastest speed reached in the last exposure, as a percentage of the athlete's max velocity.",
               "The hamstring is not back until it has sprinted at over 95% of max, repeatedly, "
               "without a reaction.", lo=0, hi=110, devices=("catapult", "kinexon", "timing_gates"),
               symbol="hare.fill"))
_m(MeasureSpec("adductor_squeeze", "Adductor squeeze", "N", True,
               "Supine squeeze on the ForceFrame or a sphygmomanometer, per side where the device allows.",
               "Groin strength and the morning-after signal: a 15% drop from baseline means pull back.",
               sided=True, lo=0, hi=800, devices=("forceframe", "dynamometer"), symbol="dumbbell.fill",
               test_key="hip_adduction_force"))
_m(MeasureSpec("hagos_sport", "HAGOS sport", "/100", True, "The Copenhagen Hip and Groin Outcome Score, sport subscale.",
               "Groin function in sport.", kind="score", lo=0, hi=100, symbol="doc.text"))
_m(MeasureSpec("hip_ir_rom", "Hip internal rotation", "°", True,
               "Seated, knee at 90°; rotate the lower leg outward. Both hips.",
               "Hip rotation loss is the hallmark of groin and pubic overload.", sided=True, lo=0,
               hi=60, phone=True, devices=("phone", "goniometer"), symbol="angle",
               test_key="hip_internal_rotation"))
_m(MeasureSpec("thomas_test", "Hip flexor length (Thomas test)", "°", False,
               "Supine off the table edge, opposite knee hugged; thigh angle below horizontal. Both.",
               "Hip flexor length; a tight flexor loads the groin and the back.", sided=True,
               lo=-10, hi=30, phone=True, symbol="angle"))

# --- general --------------------------------------------------------------------------------------

_m(MeasureSpec("pain_nrs", "Pain", "/10", False,
               "Worst pain today in the injured area, 0–10.",
               "The pain-monitoring model: ≤ 3/10 during rehab loading and back to baseline by "
               "the next morning. Above that, the step was too big.", lo=0, hi=10, symbol="bandage.fill"))
_m(MeasureSpec("pain_next_morning", "Next-morning pain", "/10", False,
               "Pain in the injured area the morning after a session, 0–10.",
               "The tendon's verdict on yesterday. Higher than the day before means the load was too much.",
               lo=0, hi=10, symbol="sunrise.fill"))
_m(MeasureSpec("swelling_grade", "Swelling", "grade", False,
               "0 none, 1 mild, 2 moderate, 3 marked, by the athletic trainer or the athlete.",
               "Swelling gates loading in every joint.", kind="grade", lo=0, hi=3, symbol="drop.fill"))
_m(MeasureSpec("rom_pct", "Range of motion, % of other side", "%", True,
               "The joint's range as a percentage of the uninjured side.",
               "Range before strength, strength before power.", lo=0, hi=120, symbol="angle"))
_m(MeasureSpec("strength_lsi", "Strength symmetry", "%", True,
               "Involved over uninvolved peak force on the relevant test.",
               "Symmetry is the return gate across injuries: 90% to return, 80% to run.", lo=0, hi=130,
               symbol="scale.3d"))
_m(MeasureSpec("rts_confidence", "Confidence to return", "/10", True,
               "How confident the athlete feels about returning, 0–10.",
               "A quick stand-in for the ACL-RSI outside the knee.", lo=0, hi=10, symbol="brain.head.profile"))
_m(MeasureSpec("symptom_score", "Symptom score (SCAT6)", "/132", False,
               "The 22-item symptom evaluation, severity 0–132.",
               "Must be at baseline (typically 0–2) before each step of the return.", kind="score",
               lo=0, hi=132, symbol="brain.head.profile"))
_m(MeasureSpec("exertion_symptoms", "Symptoms with exertion", "yes/no", False,
               "Any symptom provoked during the stepwise exertion test.",
               "No symptoms at the current step for 24 hours before the next.", kind="yes_no",
               lo=0, hi=1, symbol="heart.fill"))
_m(MeasureSpec("reaction_time", "Reaction time", "ms", False,
               "The phone's tap test; median of ten.",
               "Slows after a head knock and with poor sleep; back to baseline is a return gate.",
               lo=100, hi=600, phone=True, devices=("phone",), symbol="timer", test_key="reaction_time"))
_m(MeasureSpec("odi", "Oswestry (ODI)", "%", False, "The Oswestry Disability Index.",
               "Back-related disability; under 20% is minimal.", kind="score", lo=0, hi=100, symbol="doc.text"))
_m(MeasureSpec("shoulder_ir", "Shoulder internal rotation", "°", True,
               "Supine, 90° abduction; rotate toward the floor. Both shoulders.",
               "A dominant-side deficit over 18° (GIRD) is the overhead athlete's risk marker.",
               sided=True, lo=0, hi=100, phone=True, symbol="angle", test_key="shoulder_ir_rom"))
_m(MeasureSpec("shoulder_er_ir_ratio", "ER:IR strength ratio", "", True,
               "Dynamometer external over internal rotation strength at 90° abduction.",
               "Cuff balance; ≥ 0.66 to return to serving.", sided=True, lo=0, hi=1.5, decimals=2,
               symbol="dumbbell.fill", test_key="shoulder_er_ir_ratio"))
_m(MeasureSpec("kjoc", "KJOC shoulder & elbow", "/100", True,
               "The Kerlan-Jobe Orthopaedic Clinic overhead athlete score, 0–100.",
               "Overhead function; ≥ 90 at return.", kind="score", lo=0, hi=100, symbol="doc.text"))
_m(MeasureSpec("prtee", "PRTEE", "/100", False, "Patient-Rated Tennis Elbow Evaluation, 0–100.",
               "Lateral elbow pain and function; lower is better.", kind="score", lo=0, hi=100,
               symbol="doc.text"))
_m(MeasureSpec("grip_strength", "Grip strength", "kg", True, "Hand dynamometer, elbow at 90°. Both hands.",
               "Pain-free grip within 10% of the other hand to return.", sided=True, lo=0, hi=90,
               decimals=1, symbol="hand.raised.fill", test_key="grip_strength"))
_m(MeasureSpec("serve_pct_max", "Serve speed reached", "% of max", True,
               "Fastest serve in the last session as a percentage of the athlete's best.",
               "The shoulder's return ladder runs from 50% to 100% of serve speed over weeks.",
               lo=0, hi=110, symbol="hare.fill"))


# ---------------------------------------------------------------------------------------------------
# Criteria, phases, injuries
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CriterionSpec:
    """One gate. ``use`` says what is compared:
    value       the latest value (involved side, for a sided measure)
    lsi         involved / uninvolved × 100, inverted for lower-is-better measures
    diff        involved − uninvolved (for ranges and girths), in the measure's unit
    days        days since surgery (or injury when there is no surgery)
    """
    measure_key: str
    op: str          # >= | <= | == | <
    value: float
    label: str
    use: str = "value"
    weight: float = 1.0
    # Shown only when this is a return-to-sport criterion, not a phase exit.
    rts: bool = False


@dataclass(frozen=True)
class PhaseSpec:
    number: int
    name: str
    window: str
    goals: tuple[str, ...]
    focus: tuple[str, ...]
    exit_criteria: tuple[CriterionSpec, ...]
    weeks_min: int = 0
    # What a normal week in this phase looks like, for the plan writer.
    sessions: tuple[str, ...] = ()
    # What is still off limits.
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class InjurySpec:
    key: str
    label: str
    body_region: str
    symbol: str
    summary: str
    phases: tuple[PhaseSpec, ...]
    measures: tuple[str, ...]
    rts_criteria: tuple[CriterionSpec, ...]
    typical_return_weeks: tuple[int, int]
    sports: tuple[str, ...] = ()
    surgical: bool = False
    grafts: tuple[str, ...] = ()
    grades: tuple[str, ...] = ()
    sport_progression: tuple[str, ...] = ()
    reinjury_note: str = ""
    sources: tuple[str, ...] = ()
    # Which core performance tests should be re-baselined at return.
    retest: tuple[str, ...] = ()
    # The clinic engine's procedure type when the athlete had surgery.
    procedure_type: str | None = None
    # Whether the injury takes the athlete out of practice by itself. An
    # overuse tendon is managed in training, so the engine caps it at
    # "modified"; the staff can still set "out".
    sidelines: bool = True


INJURIES: dict[str, InjurySpec] = {}


def _i(spec: InjurySpec) -> None:
    INJURIES[spec.key] = spec


C = CriterionSpec

# --- ACL reconstruction ---------------------------------------------------------------------------

_i(InjurySpec(
    "acl_reconstruction", "ACL reconstruction", "knee", "figure.walk.motion",
    "A rebuilt ligament, nine months to a year, and the most criteria-driven return in sport. "
    "Every phase has a gate; the calendar is the floor, not the clock.",
    phases=(
        PhaseSpec(1, "Protect and wake the quad", "Weeks 0–2",
                  goals=("Full extension", "Flexion to 90°", "Effusion down to 1+ or less",
                         "Straight-leg raise without lag", "Walk without crutches"),
                  focus=("Heel props and prone hangs for extension", "Quad sets, NMES on the quad",
                         "Patellar mobilisation", "Ankle pumps, calf raises double leg",
                         "Weight-bearing as tolerated with crutches"),
                  exit_criteria=(C("knee_extension_deficit", "<=", 2, "Extension within 2° of the other knee"),
                                 C("knee_flexion", ">=", 90, "Flexion 90° or more"),
                                 C("effusion_grade", "<=", 1, "Effusion 1+ or less"),
                                 C("slr_lag", "<=", 0, "Straight-leg raise with no lag")),
                  weeks_min=1,
                  avoid=("Open-chain knee extension below 45° (hamstring graft: none)", "Running", "Pivoting")),
        PhaseSpec(2, "Range and control", "Weeks 2–6",
                  goals=("Flexion to 120°+", "Normal gait", "Effusion trace or less",
                         "Single-leg stance 30 s", "Quad strength building"),
                  focus=("Closed-chain squats to 60°, leg press, step-ups", "Bike for range",
                         "Hamstring isometrics (from week 4 with a hamstring graft)",
                         "Balance: single-leg stance progressions", "Hip and trunk work"),
                  exit_criteria=(C("knee_flexion", ">=", 125, "Flexion 125° or more"),
                                 C("knee_extension_deficit", "<=", 0, "Full extension"),
                                 C("effusion_grade", "<=", 0.5, "Effusion trace or less"),
                                 C("quad_strength", ">=", 60, "Quad strength ≥ 60% of the other leg", use="lsi"),
                                 C("calf_raise_reps", ">=", 20, "20 single-leg calf raises"),
                                 C("single_leg_balance_s", ">=", 9, "Eyes-closed balance 9 s or more"),
                                 C("pain_nrs", "<=", 3, "Pain 3/10 or less")),
                  weeks_min=4,
                  avoid=("Running", "Jumping", "Cutting")),
        PhaseSpec(3, "Strength", "Weeks 6–12",
                  goals=("Quad LSI 80% to start running (70% for pool or anti-gravity jogging)", "Full flexion",
                         "Single-leg squat with control", "Hamstring LSI 80%"),
                  focus=("Progressive loading: squats, deadlifts, single-leg press, Nordics",
                         "Leg extension in the 90–45° range", "Bike and swim conditioning",
                         "Pool running, then anti-gravity treadmill", "Landing mechanics drills, double leg"),
                  exit_criteria=(C("quad_strength", ">=", 80, "Quad LSI ≥ 80% (the return-to-running gate)", use="lsi"),
                                 C("knee_flexion", ">=", 135, "Flexion 135° or more"),
                                 C("effusion_grade", "<=", 0, "No effusion"),
                                 C("hamstring_strength", ">=", 80, "Hamstring LSI ≥ 80%", use="lsi"),
                                 C("ikdc", ">=", 64, "IKDC above 64 (tolerates a running block)"),
                                 C("__days", ">=", 84, "At least 12 weeks since surgery", use="days")),
                  weeks_min=10,
                  avoid=("Cutting", "Contact", "Plyometrics on one leg")),
        PhaseSpec(4, "Run, jump, land", "Months 3–6",
                  goals=("Running no more than three days a week, to full speed", "Plyometric contacts 50 → 100 → 150 → 200 a session",
                         "Hop battery LSI 85%", "Clean landings on video (LESS under 5)", "Pre-planned cutting at 45°, then 90°"),
                  focus=("Running progression: anti-gravity or walk–jog, intervals, continuous, then speed",
                         "Plyometrics: double leg (50 contacts), then single leg, alternate days",
                         "Change of direction, pre-planned, from 45°", "Heavy strength: 3–5 rep ranges",
                         "Sport skill without contact"),
                  exit_criteria=(C("quad_strength", ">=", 85, "Quad LSI ≥ 85%", use="lsi"),
                                 C("hop_single", ">=", 85, "Single hop LSI ≥ 85%", use="lsi"),
                                 C("single_leg_cmj", ">=", 85, "Single-leg jump LSI ≥ 85%", use="lsi"),
                                 C("__days", ">=", 168, "At least 6 months since surgery", use="days")),
                  weeks_min=24,
                  avoid=("Contact", "Unplanned cutting", "Full practice")),
        PhaseSpec(5, "Return to sport", "Months 6–9+",
                  goals=("Quad LSI 90% (100% for a pivoting sport, per Aspetar)", "All four hops LSI 90%, fresh and fatigued",
                         "ACL-RSI 65+ and TSK-11 18 or under", "IKDC 85+", "Reactive agility, contact, then full practice"),
                  focus=("Reactive and unplanned change of direction", "Contact progressions",
                         "Practice: individual, then team, then live", "Keep heavy strength twice a week",
                         "Psychological readiness work"),
                  exit_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_triple", ">=", 90, "Triple hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_crossover", ">=", 90, "Crossover hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_timed_6m", ">=", 90, "6 m timed hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("acl_rsi", ">=", 65, "ACL-RSI 65 or more", rts=True),
                                 C("tampa_tsk", "<=", 18, "TSK-11 18 or under", rts=True),
                                 C("ikdc", ">=", 85, "IKDC 85 or more", rts=True),
                                 C("__days", ">=", 270, "At least 9 months since surgery", use="days", rts=True)),
                  weeks_min=36),
        PhaseSpec(6, "Back, and watched", "Year 1–2",
                  goals=("Full competition", "Quad LSI held above 90%", "Secondary prevention twice a week"),
                  focus=("Neuromuscular warm-up every session", "Strength maintenance",
                         "Quarterly retest of the hop battery and quad strength"),
                  exit_criteria=(), weeks_min=52),
    ),
    measures=("knee_extension_deficit", "knee_flexion", "effusion_grade", "slr_lag", "quad_strength",
              "hamstring_strength", "pain_nrs", "calf_raise_reps", "single_leg_balance_s", "hop_single",
              "hop_triple", "hop_crossover", "hop_timed_6m", "single_leg_cmj", "y_balance_anterior_diff",
              "knee_valgus_dvj", "acl_rsi", "tampa_tsk", "ikdc", "koos_sport"),
    rts_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                  C("hamstring_strength", ">=", 90, "Hamstring LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_triple", ">=", 90, "Triple hop LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_crossover", ">=", 90, "Crossover hop LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_timed_6m", ">=", 90, "6 m timed hop LSI ≥ 90%", use="lsi", rts=True),
                  C("single_leg_cmj", ">=", 90, "Single-leg jump LSI ≥ 90%", use="lsi", rts=True),
                  C("acl_rsi", ">=", 65, "ACL-RSI ≥ 65", rts=True),
                  C("tampa_tsk", "<=", 18, "TSK-11 ≤ 18", rts=True),
                  C("ikdc", ">=", 85, "IKDC ≥ 85", rts=True),
                  C("effusion_grade", "<=", 0, "No effusion", rts=True),
                  C("knee_extension_deficit", "<=", 0, "Full extension", rts=True),
                  C("__days", ">=", 270, "≥ 9 months since surgery", use="days", rts=True)),
    typical_return_weeks=(36, 52), surgical=True,
    grafts=("Bone–patellar tendon–bone", "Hamstring", "Quadriceps tendon", "Allograft"),
    sport_progression=("Straight-line running", "Pre-planned cutting at 45°", "Pre-planned cutting at 90°",
                       "Reactive agility", "Non-contact practice", "Contact practice", "Scrimmage",
                       "Limited minutes", "Full minutes"),
    reinjury_note="Each month of delay to nine months cut reinjury 51% in the Delaware–Oslo cohort, and "
                  "every point of quad symmetry cut it 3%. Not meeting all six Aspetar discharge criteria "
                  "raised graft rupture fourfold in professionals. Passing is necessary, not sufficient: "
                  "about one in five athletes under 25 who return to pivoting sport tear an ACL again, so "
                  "the prevention programme stays after clearance.",
    sources=("Grindem et al. 2016 BJSM (Delaware–Oslo)", "Kyritsis et al. 2016 BJSM (Aspetar criteria)",
             "Melbourne ACL Rehabilitation Guide 2.0", "Aspetar ACL rehabilitation guideline 2023",
             "Buckthorpe & Della Villa 2021 (plyometric stages)", "Sadeqi 2018 / Webster & Feller 2018 (ACL-RSI)",
             "Muller 2016 (IKDC PASS 75.9)"),
    retest=("cmj_height", "single_leg_cmj", "pro_agility_5_10_5", "cod_505", "knee_extension_iso",
            "hop_single_distance"),
    procedure_type="ACL",
))

# --- ACL non-operative --------------------------------------------------------------------------------

_i(InjurySpec(
    "acl_nonop", "ACL tear, non-operative", "knee", "figure.walk.motion",
    "Coper pathway: the same criteria without the graft timeline, and a watch for giving-way.",
    phases=(
        PhaseSpec(1, "Settle the knee", "Weeks 0–3",
                  goals=("Full extension", "Effusion trace", "Quad activation"),
                  focus=("Extension work", "Quad sets and NMES", "Bike"),
                  exit_criteria=(C("knee_extension_deficit", "<=", 2, "Extension within 2°"),
                                 C("effusion_grade", "<=", 1, "Effusion 1+ or less"))),
        PhaseSpec(2, "Strength and neuromuscular training", "Weeks 3–10",
                  goals=("Quad LSI 80%", "Hop LSI 80%", "No giving way"),
                  focus=("Progressive strength", "Perturbation training", "Landing mechanics"),
                  exit_criteria=(C("quad_strength", ">=", 80, "Quad LSI ≥ 80%", use="lsi"),
                                 C("hop_single", ">=", 80, "Single hop LSI ≥ 80%", use="lsi")),
                  weeks_min=6),
        PhaseSpec(3, "Return to sport", "Weeks 10+",
                  goals=("Quad LSI 90%", "Hop battery 90%", "Confidence"),
                  focus=("Cutting progressions", "Sport practice"),
                  exit_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("acl_rsi", ">=", 65, "ACL-RSI ≥ 65", rts=True)),
                  weeks_min=10),
    ),
    measures=("knee_extension_deficit", "knee_flexion", "effusion_grade", "quad_strength", "hop_single",
              "hop_triple", "hop_crossover", "hop_timed_6m", "acl_rsi", "ikdc", "pain_nrs"),
    rts_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_crossover", ">=", 90, "Crossover hop LSI ≥ 90%", use="lsi", rts=True),
                  C("acl_rsi", ">=", 65, "ACL-RSI ≥ 65", rts=True)),
    typical_return_weeks=(10, 20),
    sources=("Delaware–Oslo cohort (Grindem 2018)",),
))

# --- meniscus -------------------------------------------------------------------------------------

_i(InjurySpec(
    "meniscus_repair", "Meniscus repair", "knee", "figure.walk.motion",
    "A repaired meniscus is protected from deep flexion and impact while it heals; return at four to six months.",
    phases=(
        PhaseSpec(1, "Protect the repair", "Weeks 0–4",
                  goals=("Extension full", "Flexion to 90°", "Effusion down"),
                  focus=("Brace, partial weight-bearing per surgeon", "Quad sets, SLR", "Patellar mobs"),
                  exit_criteria=(C("knee_extension_deficit", "<=", 2, "Extension within 2°"),
                                 C("knee_flexion", ">=", 90, "Flexion ≥ 90°"),
                                 C("effusion_grade", "<=", 1, "Effusion 1+ or less")),
                  avoid=("Flexion past 90° under load", "Squatting", "Twisting")),
        PhaseSpec(2, "Range and strength", "Weeks 4–10",
                  goals=("Flexion 120°+", "Normal gait", "Quad LSI 70%"),
                  focus=("Closed chain to 70°", "Bike", "Balance"),
                  exit_criteria=(C("knee_flexion", ">=", 120, "Flexion ≥ 120°"),
                                 C("quad_strength", ">=", 70, "Quad LSI ≥ 70%", use="lsi"),
                                 C("effusion_grade", "<=", 0.5, "Effusion trace or less")),
                  weeks_min=4, avoid=("Running", "Deep squats under load")),
        PhaseSpec(3, "Run and load", "Months 3–4",
                  goals=("Quad LSI 85%", "Hop LSI 85%", "Running to speed"),
                  focus=("Running progression", "Plyometrics", "Heavy strength"),
                  exit_criteria=(C("quad_strength", ">=", 85, "Quad LSI ≥ 85%", use="lsi"),
                                 C("hop_single", ">=", 85, "Single hop LSI ≥ 85%", use="lsi"),
                                 C("__days", ">=", 84, "At least 12 weeks since surgery", use="days")),
                  weeks_min=12),
        PhaseSpec(4, "Return to sport", "Months 4–6",
                  goals=("Hop battery 90%", "Cutting and contact"),
                  focus=("Change of direction", "Practice progression"),
                  exit_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("__days", ">=", 120, "At least 4 months since surgery", use="days", rts=True)),
                  weeks_min=16),
    ),
    measures=("knee_extension_deficit", "knee_flexion", "effusion_grade", "quad_strength", "hop_single",
              "hop_triple", "pain_nrs", "ikdc", "koos_sport"),
    rts_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("effusion_grade", "<=", 0, "No effusion", rts=True),
                  C("__days", ">=", 120, "≥ 4 months since surgery", use="days", rts=True)),
    typical_return_weeks=(16, 26), surgical=True, procedure_type="MENISCUS",
    retest=("cmj_height", "single_leg_cmj", "cod_505"),
))

_i(InjurySpec(
    "meniscectomy", "Partial meniscectomy", "knee", "figure.walk.motion",
    "Trimmed, not repaired: a faster return, gated by swelling and quad strength rather than healing.",
    phases=(
        PhaseSpec(1, "Settle", "Weeks 0–2",
                  goals=("Full extension", "Flexion 110°", "Effusion trace", "Normal gait"),
                  focus=("Range work", "Quad activation", "Bike"),
                  exit_criteria=(C("knee_extension_deficit", "<=", 0, "Full extension"),
                                 C("knee_flexion", ">=", 110, "Flexion ≥ 110°"),
                                 C("effusion_grade", "<=", 0.5, "Effusion trace or less"))),
        PhaseSpec(2, "Strength and run", "Weeks 2–5",
                  goals=("Quad LSI 80%", "Jogging without swelling"),
                  focus=("Progressive strength", "Running progression", "Landing drills"),
                  exit_criteria=(C("quad_strength", ">=", 80, "Quad LSI ≥ 80%", use="lsi"),
                                 C("effusion_grade", "<=", 0, "No effusion after running")),
                  weeks_min=2),
        PhaseSpec(3, "Return to sport", "Weeks 4–8",
                  goals=("Quad LSI 90%", "Hop LSI 90%"),
                  focus=("Cutting", "Practice progression"),
                  exit_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True)),
                  weeks_min=4),
    ),
    measures=("knee_extension_deficit", "knee_flexion", "effusion_grade", "quad_strength", "hop_single", "pain_nrs"),
    rts_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("effusion_grade", "<=", 0, "No effusion", rts=True)),
    typical_return_weeks=(4, 8), surgical=True, procedure_type="MENISCUS",
))

# --- patellar tendinopathy -----------------------------------------------------------------------------

_i(InjurySpec(
    "patellar_tendinopathy", "Patellar tendinopathy (jumper's knee)", "knee", "bolt.heart.fill",
    "The jumper's tendon. Managed, not rested: isometrics for pain, heavy slow resistance for the "
    "tendon, and jump load counted so it never spikes.",
    phases=(
        PhaseSpec(1, "Calm it down", "Weeks 0–2",
                  goals=("Decline squat pain in the acceptable zone (5/10 or under)", "Jump load cut by 30–50%"),
                  focus=("Isometric holds: 5 × 45 s at 70% MVC, Spanish squat or leg extension",
                         "Reduce jumps and plyometrics; keep strength and conditioning", "Calf and hip strength"),
                  exit_criteria=(C("decline_squat_pain", "<=", 5, "Decline squat pain ≤ 5/10"),
                                 C("pain_next_morning", "<=", 3, "Next-morning pain ≤ 3/10")),
                  avoid=("Plyometric volume", "Back-to-back jump days")),
        PhaseSpec(2, "Heavy slow resistance", "Weeks 2–8",
                  goals=("VISA-P rising", "Pain stable through loading", "Quad strength up"),
                  focus=("Heavy slow resistance 3×/week: squat, leg press, hack squat, 3 s up 3 s down",
                         "Isometrics on the other days", "Gradual jump count back toward usual"),
                  exit_criteria=(C("visa_p", ">=", 70, "VISA-P 70 or more"),
                                 C("decline_squat_pain", "<=", 2, "Decline squat pain ≤ 2/10"),
                                 C("quad_strength", ">=", 85, "Quad LSI ≥ 85%", use="lsi")),
                  weeks_min=2),
        PhaseSpec(3, "Energy storage", "Weeks 6–12",
                  goals=("VISA-P 80+", "Full jump load tolerated with the pain rule"),
                  focus=("Plyometric progression every 2–3 days", "Jump load back to the usual week",
                         "Keep heavy slow resistance twice a week"),
                  exit_criteria=(C("visa_p", ">=", 80, "VISA-P 80 or more"),
                                 C("decline_squat_pain", "<=", 2, "Decline squat pain ≤ 2/10"),
                                 C("pain_next_morning", "<=", 2, "Next-morning pain ≤ 2/10")),
                  weeks_min=6),
        PhaseSpec(4, "Return and maintain", "Ongoing",
                  goals=("VISA-P 90+", "Jump load managed week to week"),
                  focus=("Two tendon-loading sessions a week for the season", "Watch jump count and landing intensity"),
                  exit_criteria=(C("visa_p", ">=", 90, "VISA-P 90 or more", rts=True),), weeks_min=8),
    ),
    measures=("decline_squat_pain", "pain_next_morning", "visa_p", "quad_strength", "pain_nrs"),
    rts_criteria=(C("visa_p", ">=", 80, "VISA-P ≥ 80", rts=True),
                  C("decline_squat_pain", "<=", 2, "Decline squat pain ≤ 2/10", rts=True),
                  C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True)),
    typical_return_weeks=(6, 16), sports=("basketball", "tennis", "soccer"),
    sources=("Malliaras et al. 2015 JOSPT", "Rio et al. 2015 (isometrics)", "Kongsgaard 2009 (heavy slow resistance)",
             "Silbernagel 2007 (pain-monitoring model)", "Visentini 1998 (VISA-P, MCID 13)"), sidelines=False
))

_i(InjurySpec(
    "patellofemoral_pain", "Patellofemoral pain", "knee", "bolt.heart.fill",
    "Anterior knee pain with squatting, stairs and sitting. Hip and quad strength, load management, "
    "and a running or jumping volume that the knee can keep up with.",
    phases=(
        PhaseSpec(1, "Settle and strengthen the hip", "Weeks 0–4",
                  goals=("Pain ≤ 3/10 with daily tasks", "Hip abduction strength up"),
                  focus=("Hip abductor and external rotator strength", "Quad isometrics",
                         "Taping or bracing if it helps", "Trim the volume that provokes it"),
                  exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10"), C("kujala", ">=", 70, "Kujala ≥ 70"))),
        PhaseSpec(2, "Load the knee", "Weeks 4–10",
                  goals=("Kujala 85+", "Squat and step-down pain-free", "Quad LSI 90%"),
                  focus=("Progressive squatting and step-downs", "Running progression", "Landing control"),
                  exit_criteria=(C("kujala", ">=", 85, "Kujala ≥ 85", rts=True),
                                 C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                                 C("pain_nrs", "<=", 2, "Pain ≤ 2/10", rts=True)), weeks_min=4),
    ),
    measures=("pain_nrs", "kujala", "quad_strength", "hop_single"),
    rts_criteria=(C("kujala", ">=", 85, "Kujala ≥ 85", rts=True),
                  C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True)),
    typical_return_weeks=(4, 12), sidelines=False
))

_i(InjurySpec(
    "mcl_sprain", "MCL sprain", "knee", "figure.walk.motion",
    "The inside ligament of the knee, graded 1–3. Heals with a brace and progressive loading; "
    "return runs from one week to three months by grade.",
    phases=(
        PhaseSpec(1, "Protect", "Grade 1: days 0–5 · Grade 2: weeks 0–2 · Grade 3: weeks 0–4",
                  goals=("Swelling down", "Full extension", "Flexion 90°+", "Walk without a limp"),
                  focus=("Hinged brace per grade", "Quad sets, SLR", "Range within pain"),
                  exit_criteria=(C("swelling_grade", "<=", 1, "Swelling mild or less"),
                                 C("knee_extension_deficit", "<=", 2, "Extension within 2°"),
                                 C("knee_flexion", ">=", 100, "Flexion ≥ 100°"),
                                 C("pain_nrs", "<=", 3, "Pain ≤ 3/10"))),
        PhaseSpec(2, "Strengthen", "The next 1–4 weeks",
                  goals=("Full range", "Quad and hamstring LSI 85%", "Jogging straight ahead"),
                  focus=("Closed-chain strength", "Bike, then running progression", "Balance"),
                  exit_criteria=(C("knee_flexion", ">=", 130, "Flexion ≥ 130°"),
                                 C("quad_strength", ">=", 85, "Quad LSI ≥ 85%", use="lsi"),
                                 C("pain_nrs", "<=", 2, "Pain ≤ 2/10")), weeks_min=1),
        PhaseSpec(3, "Return to sport", "The last 1–3 weeks",
                  goals=("Lateral movement and cutting without pain", "Hop LSI 90%"),
                  focus=("Lateral and cutting drills", "Contact progression"),
                  exit_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10 with cutting", rts=True)), weeks_min=2),
    ),
    measures=("swelling_grade", "knee_extension_deficit", "knee_flexion", "quad_strength", "hop_single", "pain_nrs"),
    rts_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True)),
    typical_return_weeks=(1, 12), grades=("Grade 1", "Grade 2", "Grade 3"),
))

_i(InjurySpec(
    "patellar_dislocation", "Patellar dislocation", "knee", "figure.walk.motion",
    "A kneecap that came out. First-time episodes mostly settle without surgery in six to twelve weeks; "
    "recurrence is common in young athletes, and an MPFL reconstruction takes four to six months.",
    phases=(
        PhaseSpec(1, "Settle", "Weeks 0–3", goals=("Effusion trace", "Extension full", "Flexion 90°+", "Quad activation"),
                  focus=("Brace, quad sets and NMES", "Range within pain", "Patellar taping"),
                  exit_criteria=(C("effusion_grade", "<=", 1, "Effusion 1+ or less"),
                                 C("knee_extension_deficit", "<=", 2, "Extension within 2°"),
                                 C("knee_flexion", ">=", 90, "Flexion ≥ 90°"))),
        PhaseSpec(2, "Strength and control", "Weeks 3–8", goals=("Quad LSI 85%", "No apprehension", "Jogging"),
                  focus=("Quad and hip strength", "Single-leg squat control", "Running progression"),
                  exit_criteria=(C("quad_strength", ">=", 85, "Quad LSI ≥ 85%", use="lsi"),
                                 C("effusion_grade", "<=", 0, "No effusion"),
                                 C("kujala", ">=", 75, "Kujala ≥ 75")), weeks_min=3),
        PhaseSpec(3, "Return", "Weeks 6–12 (4–6 months after MPFL reconstruction)",
                  goals=("Hop LSI 90%", "Cutting and landing without apprehension"),
                  focus=("Hop and cut progressions", "Practice progression"),
                  exit_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("kujala", ">=", 85, "Kujala ≥ 85", rts=True)), weeks_min=6),
    ),
    measures=("effusion_grade", "knee_extension_deficit", "knee_flexion", "quad_strength", "hop_single", "kujala", "pain_nrs"),
    rts_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("kujala", ">=", 85, "Kujala ≥ 85", rts=True)),
    typical_return_weeks=(6, 24), sports=("basketball", "soccer", "tennis"),
))

_i(InjurySpec(
    "cartilage_repair", "Knee cartilage repair", "knee", "figure.walk.motion",
    "Microfracture, OATS or MACI. The slowest knee return: protected weight-bearing for six to eight weeks, "
    "impact from four to nine months, and a return gated by a quiet joint and symmetric strength.",
    phases=(
        PhaseSpec(1, "Protect", "Weeks 0–8", goals=("Range on the machine or bike", "Protected weight-bearing per surgeon"),
                  focus=("Range work", "Quad activation", "Partial weight-bearing progression"),
                  exit_criteria=(C("__days", ">=", 42, "6 weeks of protection", use="days"),
                                 C("knee_flexion", ">=", 120, "Flexion ≥ 120°")), avoid=("Impact", "Loaded flexion")),
        PhaseSpec(2, "Load", "Months 2–6", goals=("Full weight-bearing", "Quad LSI 80%", "Effusion-free after loading"),
                  focus=("Progressive strength", "Bike and pool", "Walking programme"),
                  exit_criteria=(C("quad_strength", ">=", 80, "Quad LSI ≥ 80%", use="lsi"),
                                 C("effusion_grade", "<=", 0, "No effusion"),
                                 C("__days", ">=", 120, "At least 4 months", use="days")), weeks_min=8),
        PhaseSpec(3, "Impact and return", "Months 6–12+", goals=("Running pain-free", "Hop LSI 90%", "KOOS sport 75+"),
                  focus=("Running progression", "Plyometrics, then cutting", "Practice progression"),
                  exit_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("koos_sport", ">=", 75, "KOOS sport ≥ 75", rts=True),
                                 C("__days", ">=", 180, "At least 6 months", use="days", rts=True)), weeks_min=24),
    ),
    measures=("knee_flexion", "effusion_grade", "quad_strength", "hop_single", "koos_sport", "pain_nrs"),
    rts_criteria=(C("quad_strength", ">=", 90, "Quad LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("effusion_grade", "<=", 0, "No effusion", rts=True)),
    typical_return_weeks=(26, 72), surgical=True,
))

# --- ankle -------------------------------------------------------------------------------------------

_i(InjurySpec(
    "ankle_sprain_lateral", "Lateral ankle sprain", "ankle", "figure.walk",
    "The most common injury in basketball. Days to weeks to return; months of balance work to "
    "stop the next one, because the reinjury rate without it is a coin flip.",
    phases=(
        PhaseSpec(1, "Protect and move", "Days 0–3 (grade 1) to 0–7 (grade 2–3)",
                  goals=("Swelling controlled", "Pain ≤ 3/10 walking", "Dorsiflexion returning"),
                  focus=("Compression, elevation, early movement (alphabet, pumps)",
                         "Weight-bearing as tolerated, brace or tape", "Pain-free range work"),
                  exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10"),
                                 C("ankle_girth_figure8", "<=", 2, "Swelling within 2 cm of the other ankle", use="diff"))),
        PhaseSpec(2, "Range, strength, balance", "Days 3–14",
                  goals=("Dorsiflexion within 2 cm", "Single-leg balance 30 s", "Calf raises LSI 90%",
                         "Jog straight ahead"),
                  focus=("Knee-to-wall dorsiflexion mobilisation", "Band strength all four directions",
                         "Single-leg balance progressions, eyes closed, unstable surface", "Bike, pool"),
                  exit_criteria=(C("ankle_dorsiflexion", ">=", -2, "Dorsiflexion within 2 cm of the other side", use="diff"),
                                 C("single_leg_balance_s", ">=", 10, "Eyes-closed single-leg balance ≥ 10 s"),
                                 C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi"),
                                 C("pain_nrs", "<=", 2, "Pain ≤ 2/10")), weeks_min=0),
        PhaseSpec(3, "Hop, cut, return", "Weeks 2–4",
                  goals=("Hop tests LSI 90%", "Cutting without pain", "CAIT above 25", "FAAM Sport 90%"),
                  focus=("Hopping progressions: double, single, lateral", "Change of direction",
                         "Taping or bracing for the first weeks back", "Practice progression"),
                  exit_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_lateral", ">=", 90, "Side hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("faam_sport", ">=", 90, "FAAM Sport ≥ 90%", rts=True),
                                 C("cait", ">=", 26, "CAIT 26 or more", rts=True),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)), weeks_min=1),
        PhaseSpec(4, "Prevent the next one", "Ongoing",
                  goals=("Balance training three times a week for the season"),
                  focus=("Single-leg balance and wobble-board work in warm-ups", "Brace for 6–12 months in practice"),
                  exit_criteria=(), weeks_min=3),
    ),
    measures=("pain_nrs", "ankle_girth_figure8", "swelling_grade", "ankle_dorsiflexion", "single_leg_balance_s",
              "calf_raise_reps", "sebt_composite", "hop_single", "hop_lateral", "cait", "faam_sport"),
    rts_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_lateral", ">=", 90, "Side hop LSI ≥ 90%", use="lsi", rts=True),
                  C("ankle_dorsiflexion", ">=", -2, "Dorsiflexion within 2 cm", use="diff", rts=True),
                  C("faam_sport", ">=", 90, "FAAM Sport ≥ 90%", rts=True),
                  C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)),
    typical_return_weeks=(1, 6), grades=("Grade 1", "Grade 2", "Grade 3"),
    reinjury_note="Without balance training, about a third sprain the same ankle again within a year; "
                  "with it, the risk roughly halves.",
    sources=("ROAST consensus 2018 (BJSM)", "JOSPT ankle sprain guideline 2021", "PAASS return-to-sport framework 2021",
             "Plisky 2006 (Y-balance in basketball)", "Wright 2014 (CAIT 25)"),
    retest=("ankle_dorsiflexion_ktw", "single_leg_balance", "y_balance_composite", "cod_505"),
))

_i(InjurySpec(
    "ankle_sprain_high", "High ankle sprain (syndesmosis)", "ankle", "figure.walk",
    "The ligaments above the ankle joint. Slower than a lateral sprain, and the one that cannot be rushed.",
    phases=(
        PhaseSpec(1, "Protect", "Weeks 0–2 (longer with instability)",
                  goals=("Swelling down", "Pain-free walking in a boot or brace"),
                  focus=("Boot or taping per the physician", "Range within pain", "Upper-body and bike conditioning"),
                  exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10 walking"), C("swelling_grade", "<=", 1, "Swelling mild"))),
        PhaseSpec(2, "Load", "Weeks 2–5",
                  goals=("Dorsiflexion within 2 cm", "Single-leg hop pain-free", "Jog"),
                  focus=("Progressive weight-bearing strength", "Balance", "Running progression"),
                  exit_criteria=(C("ankle_dorsiflexion", ">=", -2, "Dorsiflexion within 2 cm", use="diff"),
                                 C("single_leg_balance_s", ">=", 10, "Eyes-closed balance ≥ 10 s"),
                                 C("pain_nrs", "<=", 2, "Pain ≤ 2/10")), weeks_min=2),
        PhaseSpec(3, "Return", "Weeks 4–8+",
                  goals=("Hop LSI 90%", "Cutting pain-free"),
                  focus=("Hop and cut progressions", "Practice progression"),
                  exit_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_lateral", ">=", 90, "Side hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)), weeks_min=4),
    ),
    measures=("pain_nrs", "swelling_grade", "ankle_dorsiflexion", "single_leg_balance_s", "hop_single", "hop_lateral", "faam_sport"),
    rts_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_lateral", ">=", 90, "Side hop LSI ≥ 90%", use="lsi", rts=True),
                  C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)),
    typical_return_weeks=(4, 10),
))

_i(InjurySpec(
    "achilles_tendinopathy", "Achilles tendinopathy", "ankle", "bolt.heart.fill",
    "A sore, stiff Achilles, worst in the morning. Loaded back to health with heavy calf work and a "
    "jump volume that respects the pain rule.",
    phases=(
        PhaseSpec(1, "Calm", "Weeks 0–2",
                  goals=("Morning pain ≤ 3/10", "Isometric tolerance"),
                  focus=("Isometric calf holds 5 × 45 s", "Trim plyometric volume by a third to a half"),
                  exit_criteria=(C("pain_next_morning", "<=", 3, "Morning pain ≤ 3/10"),)),
        PhaseSpec(2, "Load", "Weeks 2–10",
                  goals=("VISA-A 70+", "Calf raise LSI 90%", "Jumping with the pain rule"),
                  focus=("Heavy slow calf raises, straight and bent knee, 3×/week", "Plyometric progression",
                         "Jump load back to usual"),
                  exit_criteria=(C("visa_a", ">=", 70, "VISA-A ≥ 70"),
                                 C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi"),
                                 C("pain_next_morning", "<=", 2, "Morning pain ≤ 2/10")), weeks_min=2),
        PhaseSpec(3, "Return and maintain", "Weeks 8+",
                  goals=("VISA-A 90+",),
                  focus=("Two loading sessions a week for the season",),
                  exit_criteria=(C("visa_a", ">=", 90, "VISA-A ≥ 90", rts=True),), weeks_min=8),
    ),
    measures=("pain_next_morning", "pain_nrs", "visa_a", "calf_raise_reps", "ankle_dorsiflexion"),
    rts_criteria=(C("visa_a", ">=", 80, "VISA-A ≥ 80", rts=True),
                  C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi", rts=True)),
    typical_return_weeks=(4, 16), sidelines=False
))

_i(InjurySpec(
    "achilles_rupture", "Achilles rupture", "ankle", "figure.walk",
    "Repaired or treated in a boot; nine to twelve months to full sport, built on calf strength.",
    phases=(
        PhaseSpec(1, "Protect", "Weeks 0–6",
                  goals=("Wound healed", "Boot weight-bearing"),
                  focus=("Boot with heel wedges, progressive weight-bearing", "Hip and knee strength"),
                  exit_criteria=(C("__days", ">=", 42, "6 weeks of protection", use="days"),), avoid=("Dorsiflexion past neutral",)),
        PhaseSpec(2, "Range and early strength", "Weeks 6–12",
                  goals=("Walk out of the boot", "Dorsiflexion to neutral and beyond", "Double-leg calf raise"),
                  focus=("Wean the boot and wedges", "Seated then standing calf work", "Bike, pool"),
                  exit_criteria=(C("ankle_dorsiflexion", ">=", 5, "Dorsiflexion ≥ 5 cm knee-to-wall"),
                                 C("calf_raise_reps", ">=", 20, "Single-leg calf raise 20 reps")), weeks_min=6),
        PhaseSpec(3, "Strength and run", "Months 3–6",
                  goals=("Calf raise LSI 80%", "Running progression"),
                  focus=("Heavy calf loading", "Running", "Hopping progression"),
                  exit_criteria=(C("calf_raise_reps", ">=", 80, "Calf raise LSI ≥ 80%", use="lsi"),
                                 C("hop_single", ">=", 80, "Single hop LSI ≥ 80%", use="lsi"),
                                 C("__days", ">=", 150, "At least 5 months", use="days")), weeks_min=12),
        PhaseSpec(4, "Return to sport", "Months 6–12",
                  goals=("Calf raise LSI 90%", "Hop battery 90%", "ATRS 80+"),
                  focus=("Plyometrics and cutting", "Practice progression"),
                  exit_criteria=(C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("atrs", ">=", 80, "ATRS ≥ 80", rts=True),
                                 C("__days", ">=", 168, "At least 24 weeks", use="days", rts=True)), weeks_min=24),
    ),
    measures=("ankle_dorsiflexion", "calf_raise_reps", "hop_single", "hop_lateral", "atrs", "pain_nrs"),
    rts_criteria=(C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("atrs", ">=", 80, "ATRS ≥ 80", rts=True)),
    typical_return_weeks=(36, 52), surgical=True, procedure_type="ANKLE",
))

# --- hamstring, groin, hip flexor, calf, quad -----------------------------------------------------------------

_i(InjurySpec(
    "hamstring_strain", "Hamstring strain", "hamstring", "figure.run",
    "Graded by the BAMIC MRI scale; two to eight weeks typically, and the injury most likely to "
    "come back if sprinting is rushed. Return runs on the H-test, Nordic strength and sprint exposure.",
    phases=(
        PhaseSpec(1, "Protect and activate", "Days 0–5",
                  goals=("Pain-free walking", "Isometric activation", "Swelling down"),
                  focus=("Pain-free isometrics at long lengths", "Trunk and hip stability", "Bike if pain-free"),
                  exit_criteria=(C("pain_nrs", "<=", 2, "Pain ≤ 2/10 walking"),), avoid=("Stretching into pain", "Running")),
        PhaseSpec(2, "Lengthen and strengthen", "Days 5–14",
                  goals=("Active knee extension within 10°", "Nordic LSI 80%", "Jogging"),
                  focus=("Eccentric lengthening: Nordics, extenders, divers, gliders (Askling)",
                         "Running progression at ≤ 70% of max speed", "Hip and trunk strength"),
                  exit_criteria=(C("hamstring_ake", "<=", 10, "Active knee extension within 10°", use="diff"),
                                 C("nordic_force", ">=", 80, "Nordic LSI ≥ 80%", use="lsi"),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10")), weeks_min=0),
        PhaseSpec(3, "Sprint", "Weeks 2–4+",
                  goals=("H-test 0/10", "Nordic LSI 90%", "Sprints at 95%+ of max, repeatedly"),
                  focus=("Progressive sprint exposure: 80, 85, 90, 95%+ of max velocity over sessions",
                         "Nordics twice a week", "Change of direction and sport drills"),
                  exit_criteria=(C("askling_h_pain", "<=", 0, "Askling H-test 0/10", rts=True),
                                 C("nordic_force", ">=", 90, "Nordic LSI ≥ 90%", use="lsi", rts=True),
                                 C("nordic_force", ">=", 337, "Nordic force above 337 N", rts=True),
                                 C("sprint_pct_max", ">=", 95, "Sprinted at ≥ 95% of max velocity", rts=True),
                                 C("pain_nrs", "<=", 0, "No pain", rts=True)), weeks_min=2),
        PhaseSpec(4, "Return and protect", "Ongoing",
                  goals=("Nordics twice a week all season", "Weekly max-velocity exposure"),
                  focus=("Nordic hamstring programme", "A sprint at 90%+ every week"),
                  exit_criteria=(), weeks_min=3),
    ),
    measures=("pain_nrs", "hamstring_ake", "nordic_force", "askling_h_pain", "sprint_pct_max", "swelling_grade"),
    rts_criteria=(C("askling_h_pain", "<=", 0, "Askling H-test 0/10", rts=True),
                  C("nordic_force", ">=", 90, "Nordic LSI ≥ 90%", use="lsi", rts=True),
                  C("sprint_pct_max", ">=", 95, "Sprinted at ≥ 95% of max", rts=True)),
    typical_return_weeks=(2, 8), grades=("Grade 0", "Grade 1", "Grade 2", "Grade 3", "Grade 4 (complete)"),
    reinjury_note="Around one in three recur, most within two weeks of return; the H-test and a real "
                  "sprint before clearance are what bring that down.",
    sources=("JOSPT hamstring strain guideline 2022", "Askling et al. 2013 (L-protocol, H-test)",
             "BAMIC (Pollock 2014)", "Timmins 2016 / Opar 2015 (Nordic force thresholds)"),
    retest=("nordic_hamstring_force", "sprint_20m", "max_speed"),
))

_i(InjurySpec(
    "adductor_groin", "Adductor-related groin pain", "groin", "figure.soccer",
    "Groin pain that squeezes and sprints hurt. The Doha classification; adductor strength is the "
    "measure, and it drops the morning after a hard session before it hurts.",
    phases=(
        PhaseSpec(1, "Settle", "Weeks 0–2",
                  goals=("Squeeze pain ≤ 3/10", "Hip range maintained"),
                  focus=("Isometric adduction holds", "Copenhagen adduction, short lever", "Trunk and hip stability",
                         "Cut change-of-direction volume"),
                  exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10 with the squeeze"),)),
        PhaseSpec(2, "Strength", "Weeks 2–6",
                  goals=("Squeeze LSI 90% or back to baseline", "HAGOS sport rising", "Running and cutting progressively"),
                  focus=("Copenhagen adduction progression, 2–3×/week", "Hip rotation range", "Running and change of direction progression"),
                  exit_criteria=(C("adductor_squeeze", ">=", 90, "Squeeze ≥ 90% of baseline / other side", use="lsi"),
                                 C("hagos_sport", ">=", 75, "HAGOS sport ≥ 75"),
                                 C("pain_nrs", "<=", 2, "Pain ≤ 2/10")), weeks_min=2),
        PhaseSpec(3, "Return", "Weeks 4–8",
                  goals=("Pain-free kicking, cutting and sprinting", "HAGOS sport 85+"),
                  focus=("Sport-specific drills", "Practice progression", "Copenhagen plank in warm-ups for the season"),
                  exit_criteria=(C("adductor_squeeze", ">=", 95, "Squeeze ≥ 95%", use="lsi", rts=True),
                                 C("hagos_sport", ">=", 85, "HAGOS sport ≥ 85", rts=True),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)), weeks_min=4),
    ),
    measures=("pain_nrs", "adductor_squeeze", "hip_ir_rom", "hagos_sport", "thomas_test"),
    rts_criteria=(C("adductor_squeeze", ">=", 95, "Squeeze ≥ 95%", use="lsi", rts=True),
                  C("hagos_sport", ">=", 85, "HAGOS sport ≥ 85", rts=True)),
    typical_return_weeks=(3, 10), sports=("soccer", "basketball", "tennis"),
    sources=("Doha agreement 2015", "Hölmich 1999 (active training)", "Copenhagen adduction (Ishøi 2016)"),
))

_i(InjurySpec(
    "hip_flexor_strain", "Hip flexor strain", "hip", "figure.run",
    "Iliopsoas or rectus femoris; sprinting and kicking are the provocations.",
    phases=(
        PhaseSpec(1, "Settle", "Days 0–5", goals=("Pain-free walking",),
                  focus=("Isometrics", "Gentle range"), exit_criteria=(C("pain_nrs", "<=", 2, "Pain ≤ 2/10"),)),
        PhaseSpec(2, "Strengthen and run", "Days 5–21",
                  goals=("Thomas test symmetric", "Jogging to striding"),
                  focus=("Hip flexor strength through range", "Running progression"),
                  exit_criteria=(C("thomas_test", "<=", 5, "Hip flexor length within 5°", use="diff"),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10")), weeks_min=0),
        PhaseSpec(3, "Return", "Weeks 2–5", goals=("Sprint and kick pain-free",),
                  focus=("Sprint exposure", "Sport drills"),
                  exit_criteria=(C("sprint_pct_max", ">=", 95, "Sprinted at ≥ 95%", rts=True),
                                 C("pain_nrs", "<=", 0, "No pain", rts=True)), weeks_min=2),
    ),
    measures=("pain_nrs", "thomas_test", "sprint_pct_max"),
    rts_criteria=(C("sprint_pct_max", ">=", 95, "Sprinted at ≥ 95%", rts=True),),
    typical_return_weeks=(1, 5),
))

_i(InjurySpec(
    "calf_strain", "Calf strain", "calf", "figure.run",
    "Gastrocnemius or soleus; the soleus version is slower. Calf-raise strength and a graded return to speed.",
    phases=(
        PhaseSpec(1, "Settle", "Days 0–5", goals=("Pain-free walking",),
                  focus=("Isometric calf holds", "Bike"), exit_criteria=(C("pain_nrs", "<=", 2, "Pain ≤ 2/10 walking"),)),
        PhaseSpec(2, "Strength", "Days 5–14", goals=("Calf raise LSI 80%", "Jog"),
                  focus=("Seated and standing calf raises, bent and straight knee", "Running progression ≤ 70%"),
                  exit_criteria=(C("calf_raise_reps", ">=", 80, "Calf raise LSI ≥ 80%", use="lsi"),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10")), weeks_min=0),
        PhaseSpec(3, "Return", "Weeks 2–4", goals=("Calf raise LSI 90%", "Sprint and jump pain-free"),
                  focus=("Hopping and sprint exposure",),
                  exit_criteria=(C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("pain_nrs", "<=", 0, "No pain", rts=True)), weeks_min=2),
    ),
    measures=("pain_nrs", "calf_raise_reps", "hop_single", "ankle_dorsiflexion"),
    rts_criteria=(C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi", rts=True),
                  C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True)),
    typical_return_weeks=(1, 6),
))

_i(InjurySpec(
    "quad_contusion", "Quadriceps contusion", "thigh", "figure.run",
    "A knee in the thigh. Range is the measure: flexion back to 120° fast, and no myositis.",
    phases=(
        PhaseSpec(1, "Protect", "Days 0–3", goals=("Knee flexion 90°+ pain-free",),
                  focus=("Ice and compression in flexion", "Gentle range"),
                  exit_criteria=(C("knee_flexion", ">=", 90, "Flexion ≥ 90°"),), avoid=("Massage", "Heat")),
        PhaseSpec(2, "Range and strength", "Days 3–10", goals=("Flexion within 10° of the other side", "Jog"),
                  focus=("Bike", "Progressive quad strength", "Running"),
                  exit_criteria=(C("knee_flexion", ">=", -10, "Flexion within 10°", use="diff"),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10")), weeks_min=0),
        PhaseSpec(3, "Return", "Days 7–21", goals=("Full range", "Sprint and jump"),
                  focus=("Sport drills", "Protective padding"),
                  exit_criteria=(C("knee_flexion", ">=", -5, "Flexion within 5°", use="diff", rts=True),
                                 C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True)), weeks_min=1),
    ),
    measures=("knee_flexion", "pain_nrs", "hop_single", "quad_strength"),
    rts_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),),
    typical_return_weeks=(1, 4), sports=("soccer", "basketball"),
))

# --- bone, back, head ---------------------------------------------------------------------------------------

_i(InjurySpec(
    "stress_fracture_foot", "Foot stress fracture (navicular / fifth metatarsal)", "foot", "figure.walk",
    "The basketball bone injuries: navicular and Jones fractures, often fixed with a screw. Six to "
    "twelve weeks, imaging-led, with bone health and shoe fit checked on the way back.",
    phases=(
        PhaseSpec(1, "Unload", "Weeks 0–6", goals=("Pain-free in the boot", "Fitness kept on the bike and in the pool"),
                  focus=("Boot or surgery per the physician", "Non-impact conditioning", "Vitamin D, calcium, energy availability review"),
                  exit_criteria=(C("__days", ">=", 42, "6 weeks of unloading", use="days"), C("pain_nrs", "<=", 0, "No pain walking")),
                  avoid=("Impact",)),
        PhaseSpec(2, "Reload", "Weeks 6–10", goals=("Walk-jog progression pain-free", "Calf raise LSI 90%"),
                  focus=("Graded impact: walking, then alternating jog", "Calf and foot strength"),
                  exit_criteria=(C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi"),
                                 C("pain_next_morning", "<=", 0, "No next-morning pain")), weeks_min=6),
        PhaseSpec(3, "Return", "Weeks 10–16", goals=("Hop and cut pain-free", "Imaging healed"),
                  focus=("Hopping, cutting, practice progression"),
                  exit_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("pain_nrs", "<=", 0, "No pain", rts=True)), weeks_min=10),
    ),
    measures=("pain_nrs", "pain_next_morning", "calf_raise_reps", "hop_single"),
    rts_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                  C("pain_nrs", "<=", 0, "No pain", rts=True)),
    typical_return_weeks=(6, 16), sports=("basketball", "soccer", "tennis"),
))

_i(InjurySpec(
    "tibial_stress", "Tibial stress injury (shin)", "shin", "figure.walk",
    "From shin splints to a stress fracture. Load, bone health and running mechanics.",
    phases=(
        PhaseSpec(1, "Unload", "Weeks 0–3", goals=("Pain-free walking",),
                  focus=("Cut impact to pain-free", "Bike and pool", "Energy availability review"),
                  exit_criteria=(C("pain_nrs", "<=", 0, "No pain walking"),)),
        PhaseSpec(2, "Reload", "Weeks 3–8", goals=("Jogging pain-free", "Calf strength"),
                  focus=("Graded impact progression", "Calf and hip strength"),
                  exit_criteria=(C("pain_next_morning", "<=", 0, "No next-morning pain"),
                                 C("calf_raise_reps", ">=", 90, "Calf raise LSI ≥ 90%", use="lsi")), weeks_min=3),
        PhaseSpec(3, "Return", "Weeks 6–12", goals=("Full impact pain-free",),
                  focus=("Jumping and cutting progression",),
                  exit_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),
                                 C("pain_nrs", "<=", 0, "No pain", rts=True)), weeks_min=6),
    ),
    measures=("pain_nrs", "pain_next_morning", "calf_raise_reps", "hop_single"),
    rts_criteria=(C("hop_single", ">=", 90, "Single hop LSI ≥ 90%", use="lsi", rts=True),),
    typical_return_weeks=(3, 12), sidelines=False
))

_i(InjurySpec(
    "low_back_pain", "Low back pain", "back", "figure.walk",
    "Mechanical back pain, or a stress reaction of the pars in a young athlete. Movement, hip "
    "mobility and trunk endurance; disability tracked on the Oswestry.",
    phases=(
        PhaseSpec(1, "Settle", "Weeks 0–2", goals=("Pain ≤ 3/10 with daily tasks", "Walk 30 min"),
                  focus=("Keep moving", "Pain-free trunk and hip work", "Trim the provoking load"),
                  exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10"), C("odi", "<=", 30, "ODI ≤ 30%"))),
        PhaseSpec(2, "Build", "Weeks 2–6", goals=("ODI under 20%", "Hip rotation restored", "Lifting pattern restored"),
                  focus=("Trunk endurance (McGill)", "Hip mobility", "Loaded hinge progression"),
                  exit_criteria=(C("odi", "<=", 20, "ODI ≤ 20%"), C("pain_nrs", "<=", 2, "Pain ≤ 2/10")), weeks_min=2),
        PhaseSpec(3, "Return", "Weeks 4–8", goals=("Sprint, jump and rotate pain-free",),
                  focus=("Sport loading progression",),
                  exit_criteria=(C("odi", "<=", 10, "ODI ≤ 10%", rts=True), C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)), weeks_min=4),
    ),
    measures=("pain_nrs", "odi", "hip_ir_rom", "hamstring_ake"),
    rts_criteria=(C("odi", "<=", 10, "ODI ≤ 10%", rts=True), C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)),
    typical_return_weeks=(1, 10), sidelines=False
))

_i(InjurySpec(
    "concussion", "Concussion", "head", "brain.head.profile",
    "Symptoms at rest, then a stepwise return: each step 24 hours symptom-free before the next, "
    "and medical clearance before contact. The reaction-time test is the daily objective check.",
    phases=(
        PhaseSpec(1, "Relative rest", "Days 0–2", goals=("Symptoms settling", "Light walking tolerated"),
                  focus=("Relative rest, screens limited for 48 h", "Light walking", "Sleep"),
                  exit_criteria=(C("symptom_score", "<=", 10, "Symptom score ≤ 10"),), avoid=("Exertion", "Contact")),
        PhaseSpec(2, "Light aerobic", "Days 2–5", goals=("Heart rate to 55–70% max without symptoms", "Return to learn"),
                  focus=("Bike or walk, 15–20 min, no symptom rise", "School or work with breaks"),
                  exit_criteria=(C("exertion_symptoms", "<=", 0, "No symptoms with light exertion"),
                                 C("symptom_score", "<=", 5, "Symptom score ≤ 5")), weeks_min=0),
        PhaseSpec(3, "Sport-specific, no contact", "Days 4–8", goals=("Running and skills without symptoms", "Reaction time at baseline"),
                  focus=("Running drills, individual skills", "No head impact"),
                  exit_criteria=(C("exertion_symptoms", "<=", 0, "No symptoms with running"),
                                 C("symptom_score", "<=", 2, "Symptom score at baseline"),
                                 C("reaction_time", "<=", 260, "Reaction time at baseline")), weeks_min=0),
        PhaseSpec(4, "Non-contact practice", "Days 6–10", goals=("Full practice without contact",),
                  focus=("Team drills", "Resistance training"),
                  exit_criteria=(C("exertion_symptoms", "<=", 0, "No symptoms with practice"),), weeks_min=0),
        PhaseSpec(5, "Full contact after clearance", "Days 7+", goals=("Medical clearance", "Full practice"),
                  focus=("Medical clearance, then contact practice"),
                  exit_criteria=(C("exertion_symptoms", "<=", 0, "No symptoms with contact", rts=True),
                                 C("symptom_score", "<=", 2, "Symptom score at baseline", rts=True)), weeks_min=1),
    ),
    measures=("symptom_score", "exertion_symptoms", "reaction_time", "single_leg_balance_s"),
    rts_criteria=(C("symptom_score", "<=", 2, "Symptom score at baseline", rts=True),
                  C("exertion_symptoms", "<=", 0, "No symptoms with full exertion", rts=True)),
    typical_return_weeks=(1, 4),
    sources=("Amsterdam consensus 2022 (SCAT6)", "NCAA concussion safety protocol"),
))

_i(InjurySpec(
    "finger_sprain", "Finger sprain / dislocation", "hand", "hand.raised.fill",
    "The jammed finger. Buddy taping, range, grip; days to weeks.",
    phases=(
        PhaseSpec(1, "Protect", "Days 0–3", goals=("Swelling down", "Pain ≤ 3/10"),
                  focus=("Buddy tape", "Gentle range"), exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10"),)),
        PhaseSpec(2, "Return", "Days 3–14", goals=("Grip within 10%", "Ball handling pain-free"),
                  focus=("Grip and range work", "Taped ball work"),
                  exit_criteria=(C("grip_strength", ">=", 90, "Grip LSI ≥ 90%", use="lsi", rts=True),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)), weeks_min=0),
    ),
    measures=("pain_nrs", "swelling_grade", "grip_strength"),
    rts_criteria=(C("grip_strength", ">=", 90, "Grip LSI ≥ 90%", use="lsi", rts=True),),
    typical_return_weeks=(0, 3), sports=("basketball",),
))

# --- shoulder, elbow, wrist, trunk (tennis) -------------------------------------------------------------------------

_i(InjurySpec(
    "shoulder_overuse", "Serving shoulder (rotator cuff / impingement)", "shoulder", "figure.tennis",
    "The overhead athlete's shoulder: cuff strength, internal rotation range and a serve-speed ladder back.",
    phases=(
        PhaseSpec(1, "Settle", "Weeks 0–2", goals=("Pain ≤ 3/10 overhead", "IR range within 18° of the other side"),
                  focus=("Sleeper and cross-body stretches", "Cuff isometrics", "Scapular control", "No serving"),
                  exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10"),
                                 C("shoulder_ir", ">=", -18, "Internal rotation within 18°", use="diff")), avoid=("Serving", "Overheads")),
        PhaseSpec(2, "Strengthen", "Weeks 2–6", goals=("ER:IR ≥ 0.66", "KJOC 75+", "Groundstrokes"),
                  focus=("External rotation strengthening at 90°", "Scapular stabilisers", "Groundstroke progression"),
                  exit_criteria=(C("shoulder_er_ir_ratio", ">=", 0.66, "ER:IR ≥ 0.66"),
                                 C("kjoc", ">=", 75, "KJOC ≥ 75"), C("pain_nrs", "<=", 2, "Pain ≤ 2/10")), weeks_min=2),
        PhaseSpec(3, "Serve ladder", "Weeks 4–10", goals=("Serve speed from 50% to 100% over weeks", "KJOC 90+"),
                  focus=("Serves at 50, 60, 70, 80, 90, 100% of best, two sessions each", "Keep cuff work twice a week"),
                  exit_criteria=(C("serve_pct_max", ">=", 95, "Serving at ≥ 95%", rts=True),
                                 C("kjoc", ">=", 90, "KJOC ≥ 90", rts=True),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)), weeks_min=4),
    ),
    measures=("pain_nrs", "shoulder_ir", "shoulder_er_ir_ratio", "kjoc", "serve_pct_max"),
    rts_criteria=(C("serve_pct_max", ">=", 95, "Serving at ≥ 95%", rts=True), C("kjoc", ">=", 90, "KJOC ≥ 90", rts=True)),
    typical_return_weeks=(3, 12), sports=("tennis",),
    sources=("Wilk et al. (overhead athlete)", "Kibler (GIRD, total arc)", "KJOC (Alberta 2010)"), sidelines=False
))

_i(InjurySpec(
    "lateral_elbow", "Tennis elbow (lateral epicondylalgia)", "elbow", "figure.tennis",
    "Lateral elbow pain with gripping and the backhand. Loaded back with wrist extensor work; grip tracked.",
    phases=(
        PhaseSpec(1, "Settle", "Weeks 0–2", goals=("PRTEE falling", "Pain-free grip at 70%"),
                  focus=("Isometric wrist extension", "Technique and grip-size check", "Trim backhand volume"),
                  exit_criteria=(C("prtee", "<=", 40, "PRTEE ≤ 40"), C("pain_nrs", "<=", 3, "Pain ≤ 3/10"))),
        PhaseSpec(2, "Load", "Weeks 2–8", goals=("Grip LSI 90%", "PRTEE under 20"),
                  focus=("Eccentric and heavy slow wrist extensor work", "Backhand progression"),
                  exit_criteria=(C("grip_strength", ">=", 90, "Grip LSI ≥ 90%", use="lsi", rts=True),
                                 C("prtee", "<=", 20, "PRTEE ≤ 20", rts=True)), weeks_min=2),
    ),
    measures=("pain_nrs", "prtee", "grip_strength"),
    rts_criteria=(C("grip_strength", ">=", 90, "Grip LSI ≥ 90%", use="lsi", rts=True), C("prtee", "<=", 20, "PRTEE ≤ 20", rts=True)),
    typical_return_weeks=(2, 12), sports=("tennis",), sidelines=False
))

_i(InjurySpec(
    "wrist_tfcc", "Wrist (TFCC / ulnar-sided)", "wrist", "hand.raised.fill",
    "Ulnar wrist pain from the two-handed backhand and the forehand wrist snap.",
    phases=(
        PhaseSpec(1, "Protect", "Weeks 0–3", goals=("Pain ≤ 3/10 with daily use",),
                  focus=("Splint or tape", "Forearm rotation range", "No hitting"),
                  exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10"),), avoid=("Hitting",)),
        PhaseSpec(2, "Strengthen and hit", "Weeks 3–8", goals=("Grip LSI 90%", "Pain-free hitting"),
                  focus=("Grip and forearm strength", "Hitting progression"),
                  exit_criteria=(C("grip_strength", ">=", 90, "Grip LSI ≥ 90%", use="lsi", rts=True),
                                 C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)), weeks_min=3),
    ),
    measures=("pain_nrs", "grip_strength", "swelling_grade"),
    rts_criteria=(C("grip_strength", ">=", 90, "Grip LSI ≥ 90%", use="lsi", rts=True),),
    typical_return_weeks=(3, 10), sports=("tennis",),
))

_i(InjurySpec(
    "abdominal_strain", "Abdominal strain", "trunk", "figure.tennis",
    "The serving athlete's oblique or rectus strain; serving is the last thing back.",
    phases=(
        PhaseSpec(1, "Settle", "Weeks 0–2", goals=("Pain-free daily movement",),
                  focus=("Isometric trunk work", "No serving or overhead"), exit_criteria=(C("pain_nrs", "<=", 2, "Pain ≤ 2/10"),)),
        PhaseSpec(2, "Load", "Weeks 2–5", goals=("Rotational strength pain-free", "Groundstrokes"),
                  focus=("Anti-rotation and rotational strength", "Groundstroke progression"),
                  exit_criteria=(C("pain_nrs", "<=", 1, "Pain ≤ 1/10"),), weeks_min=2),
        PhaseSpec(3, "Serve ladder", "Weeks 4–8", goals=("Serve speed to 100%",),
                  focus=("Serves at 50 to 100% over sessions",),
                  exit_criteria=(C("serve_pct_max", ">=", 95, "Serving at ≥ 95%", rts=True), C("pain_nrs", "<=", 0, "No pain", rts=True)), weeks_min=4),
    ),
    measures=("pain_nrs", "serve_pct_max"),
    rts_criteria=(C("serve_pct_max", ">=", 95, "Serving at ≥ 95%", rts=True),),
    typical_return_weeks=(3, 8), sports=("tennis",),
))

_i(InjurySpec(
    "osteitis_pubis", "Pubic overload (osteitis pubis)", "groin", "figure.soccer",
    "Pubic-symphysis pain from kicking and cutting load. Weeks to months; adductor and hip strength, load management.",
    phases=(
        PhaseSpec(1, "Unload", "Weeks 0–4", goals=("Pain ≤ 3/10 with walking and squeeze",),
                  focus=("Cut kicking and cutting", "Isometric adduction, trunk stability", "Hip range"),
                  exit_criteria=(C("pain_nrs", "<=", 3, "Pain ≤ 3/10"),), avoid=("Kicking", "Cutting")),
        PhaseSpec(2, "Rebuild", "Weeks 4–10", goals=("Squeeze LSI 90%", "HAGOS 75+", "Running progression"),
                  focus=("Copenhagen adduction progression", "Running, then change of direction"),
                  exit_criteria=(C("adductor_squeeze", ">=", 90, "Squeeze ≥ 90%", use="lsi"), C("hagos_sport", ">=", 75, "HAGOS sport ≥ 75")), weeks_min=4),
        PhaseSpec(3, "Return", "Weeks 8–16", goals=("Kicking and cutting pain-free",),
                  focus=("Sport drills and practice progression",),
                  exit_criteria=(C("hagos_sport", ">=", 85, "HAGOS sport ≥ 85", rts=True), C("pain_nrs", "<=", 1, "Pain ≤ 1/10", rts=True)), weeks_min=8),
    ),
    measures=("pain_nrs", "adductor_squeeze", "hip_ir_rom", "hagos_sport"),
    rts_criteria=(C("hagos_sport", ">=", 85, "HAGOS sport ≥ 85", rts=True), C("adductor_squeeze", ">=", 95, "Squeeze ≥ 95%", use="lsi", rts=True)),
    typical_return_weeks=(6, 20), sports=("soccer",), sidelines=False
))


# --- views ---------------------------------------------------------------------------------------------------------


def injuries_for(sport: str) -> list[InjurySpec]:
    out = [i for i in INJURIES.values() if not i.sports or sport in i.sports]
    region_order = ["knee", "ankle", "foot", "shin", "hamstring", "groin", "hip", "calf", "thigh", "back",
                    "head", "hand", "shoulder", "elbow", "wrist", "trunk"]
    return sorted(out, key=lambda i: (region_order.index(i.body_region) if i.body_region in region_order else 99,
                                      i.label))


def _criterion_view(c: CriterionSpec) -> dict[str, Any]:
    return {"measure_key": c.measure_key, "op": c.op, "value": c.value, "label": c.label, "use": c.use,
            "rts": c.rts}


def injury_view(spec: InjurySpec, *, full: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": spec.key, "label": spec.label, "body_region": spec.body_region, "symbol": spec.symbol,
        "summary": spec.summary, "sports": list(spec.sports), "surgical": spec.surgical,
        "grafts": list(spec.grafts), "grades": list(spec.grades),
        "typical_return_weeks": list(spec.typical_return_weeks), "reinjury_note": spec.reinjury_note,
        "sources": list(spec.sources), "measures": list(spec.measures), "retest": list(spec.retest),
        "sidelines": spec.sidelines,
    }
    if full:
        out["phases"] = [
            {"number": p.number, "name": p.name, "window": p.window, "goals": list(p.goals),
             "focus": list(p.focus), "avoid": list(p.avoid), "weeks_min": p.weeks_min,
             "exit_criteria": [_criterion_view(c) for c in p.exit_criteria]}
            for p in spec.phases
        ]
        out["rts_criteria"] = [_criterion_view(c) for c in spec.rts_criteria]
        out["sport_progression"] = list(spec.sport_progression)
    return out


def measure_view(spec: MeasureSpec) -> dict[str, Any]:
    return {
        "key": spec.key, "label": spec.label, "unit": spec.unit, "higher_is_better": spec.higher_is_better,
        "protocol": spec.protocol, "why": spec.why, "sided": spec.sided, "kind": spec.kind,
        "lo": spec.lo, "hi": spec.hi, "decimals": spec.decimals, "phone": spec.phone,
        "devices": list(spec.devices), "symbol": spec.symbol, "test_key": spec.test_key, "mdc": spec.mdc,
    }
