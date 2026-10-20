"""Performance tests: what strength and conditioning staffs measure, and
where a level sits.

Benchmarks are reference points, not norms for this athlete: every athlete
is first compared with their own best and their own trend (the performance
board), and only then with the level. The four numbers of a benchmark are
the reference values at roughly the 25th, 50th, 75th and 90th percentile of
that level, drawn from published combine data, NSCA tables and team-sport
testing literature. Where a level has no published figure the nearest is
reused and the catalog says so (``benchmark_note``).

Sources the figures are drawn from: NBA Draft Combine results (2018–2025),
the NSCA Essentials of Strength Training & Conditioning normative tables,
Hawkin Dynamics and VALD published norms for collegiate basketball and
soccer, Yo-Yo IR1/IR2 and 30-15 IFT team-sport data (Bangsbo 2008, Buchheit
2008), USTA/ITF tennis testing protocols, and FIFA/UEFA fitness batteries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Categories, in the order the Stats tab shows them.
CATEGORIES: list[dict[str, str]] = [
    {"key": "jump", "label": "Jump & power", "symbol": "figure.jumprope", "family": "teal"},
    {"key": "speed", "label": "Speed", "symbol": "hare.fill", "family": "blue"},
    {"key": "agility", "label": "Agility & change of direction", "symbol": "arrow.triangle.swap",
     "family": "blue"},
    {"key": "strength", "label": "Strength", "symbol": "dumbbell.fill", "family": "violet"},
    {"key": "conditioning", "label": "Conditioning", "symbol": "lungs.fill", "family": "indigo"},
    {"key": "mobility", "label": "Mobility & balance", "symbol": "figure.flexibility",
     "family": "teal"},
    {"key": "body", "label": "Body", "symbol": "figure.stand", "family": "violet"},
    {"key": "skill", "label": "Skill", "symbol": "basketball.fill", "family": "blue"},
]

# A benchmark key is "<level>:<sex>"; "all" applies when nothing closer exists.
Benchmarks = dict[str, tuple[float, float, float, float]]


@dataclass(frozen=True)
class TestSpec:
    key: str
    label: str
    category: str
    unit: str
    higher_is_better: bool
    protocol: str
    why: str
    sports: tuple[str, ...] = ()          # () = every sport
    sided: bool = False                   # measured per limb
    decimals: int = 1
    devices: tuple[str, ...] = ("manual",)
    phone: bool = False                   # the app can run this test itself
    asymmetry_flag_pct: float | None = None
    # The "core battery" a program expects first; the Stats tab leads with these.
    core: bool = False
    benchmarks: Benchmarks = field(default_factory=dict)
    benchmark_note: str = ""
    aliases: tuple[str, ...] = ()


def _b(**levels: tuple[float, float, float, float]) -> Benchmarks:
    return {k.replace("__", ":"): v for k, v in levels.items()}


# ---------------------------------------------------------------------------------------
# Basketball first, then the shared tests, then tennis and soccer.
# ---------------------------------------------------------------------------------------

TESTS: dict[str, TestSpec] = {}


def _add(spec: TestSpec) -> None:
    TESTS[spec.key] = spec


# --- jump & power ----------------------------------------------------------------------

_add(TestSpec(
    "vertical_jump_standing", "Standing vertical", "jump", "in", True,
    "Standing reach is measured first; the athlete jumps from a standstill (no step) and "
    "touches the highest vane. Jump = touch height minus standing reach. Best of three.",
    "The combine number. Lower-body power without an approach, the one coaches quote.",
    sports=("basketball",), decimals=1, devices=("vertec", "manual", "force_plate"), core=True,
    benchmarks=_b(pro__M=(27.5, 30.0, 32.5, 35.0), ncaa_d1__M=(24.5, 27.0, 29.5, 32.0),
                  ncaa_d1__F=(16.0, 18.5, 21.0, 23.5), high_school__M=(19.0, 22.0, 25.0, 28.0),
                  high_school__F=(13.0, 15.5, 18.0, 20.5), pro__F=(18.0, 20.5, 23.0, 25.5)),
    benchmark_note="NBA Draft Combine, drafted players 2011–2021: no-step 30.5 ± 3.0 in (Morrison 2022); "
                   "NCAA figures from collegiate testing literature.",
))
_add(TestSpec(
    "vertical_jump_max", "Max vertical (approach)", "jump", "in", True,
    "A running approach into a two-foot (or one-foot) takeoff, touch the highest vane. "
    "Jump = touch height minus standing reach. Best of three.",
    "The approach jump is the game jump: the rebound, the block, the dunk.",
    sports=("basketball",), decimals=1, devices=("vertec", "manual"), core=True,
    benchmarks=_b(pro__M=(33.5, 36.5, 39.0, 42.0), ncaa_d1__M=(29.5, 32.0, 34.5, 37.5),
                  ncaa_d1__F=(19.0, 21.5, 24.0, 27.0), high_school__M=(23.0, 26.0, 29.0, 32.0),
                  high_school__F=(15.0, 17.5, 20.0, 23.0), pro__F=(21.0, 23.5, 26.0, 29.0)),
    benchmark_note="NBA Draft Combine drafted-player mean 36.4 in (guards 36.2, centers 31.9); the record is 46 in.",
))
_add(TestSpec(
    "cmj_height", "Countermovement jump", "jump", "cm", True,
    "Hands on hips, dip and jump for maximum height on a force plate (or with the phone's "
    "flight-time test). Three jumps, best and mean recorded.",
    "The weekly neuromuscular readiness test. A drop of more than about 10% from the "
    "athlete's baseline, with a longer time to takeoff, is fatigue before it shows anywhere else.",
    decimals=1, devices=("force_plate", "jump_mat", "vert"), phone=False, core=True,
    benchmarks=_b(pro__M=(40.0, 44.0, 48.0, 53.0), ncaa_d1__M=(38.0, 42.0, 46.0, 50.0),
                  ncaa_d1__F=(27.0, 30.5, 34.0, 38.0), high_school__M=(32.0, 36.0, 40.0, 44.0),
                  high_school__F=(22.0, 25.0, 28.5, 32.0), pro__F=(29.0, 32.5, 36.0, 40.0)),
    benchmark_note="Force-plate CMJ, hands on hips: NCAA DI men 43.6 cm guards / 41.0 forwards across seven Power Five "
                   "programs (Berberet 2024); DI women 34 cm high-minute vs 28 cm low (Philipp 2023); ACB pros 39 cm.",
    aliases=("cmj",),
))
_add(TestSpec(
    "phone_jump_height", "Jump (phone)", "jump", "cm", True,
    "Hold the phone flat against your chest, dip and jump for height, land softly on both feet. Three jumps; "
    "the app reads the flight time and keeps the best.",
    "A jump mat in your pocket. Flight-time heights read a few centimetres higher than a force plate and "
    "depend on landing like you took off, so this compares with your own phone jumps, never with the plate.",
    decimals=1, devices=("phone",), phone=True,
    benchmarks=_b(pro__M=(42.0, 46.0, 50.0, 55.0), ncaa_d1__M=(40.0, 44.0, 48.0, 52.0),
                  ncaa_d1__F=(29.0, 32.5, 36.0, 40.0), all=(30.0, 36.0, 42.0, 48.0)),
    benchmark_note="Flight-time estimate; about 2 cm above the force-plate rows.",
))
_add(TestSpec(
    "cmj_rsi_mod", "RSI-modified", "jump", "", True,
    "Jump height divided by time to takeoff, from the force plate countermovement jump.",
    "How much height per second of push: the explosiveness a bigger jump height can hide. "
    "The most sensitive of the CMJ variables to fatigue.",
    decimals=2, devices=("force_plate",), core=True,
    benchmarks=_b(pro__M=(0.50, 0.58, 0.68, 0.80), ncaa_d1__M=(0.50, 0.60, 0.68, 0.76),
                  ncaa_d1__F=(0.36, 0.44, 0.51, 0.58), high_school__M=(0.35, 0.44, 0.52, 0.60),
                  high_school__F=(0.24, 0.30, 0.37, 0.44), pro__F=(0.32, 0.40, 0.48, 0.56)),
))
_add(TestSpec(
    "cmj_time_to_takeoff", "Time to takeoff", "jump", "ms", False,
    "From the start of the countermovement to the instant the feet leave the plate.",
    "The clock on the jump. When it lengthens while height holds, the athlete is working "
    "harder for the same result: the earliest neuromuscular fatigue signal.",
    decimals=0, devices=("force_plate",),
    benchmarks=_b(all=(820.0, 740.0, 680.0, 620.0)),
    benchmark_note="NCAA DI men 670–690 ms (Berberet 2024); it lengthens with fatigue before height falls.",
))
_add(TestSpec(
    "cmj_peak_power_rel", "Relative peak power", "jump", "W/kg", True,
    "Peak concentric power in the countermovement jump, per kilogram of body mass.",
    "Power that travels with the athlete's size: the fair comparison between a guard and a post.",
    decimals=1, devices=("force_plate",),
    benchmarks=_b(pro__M=(54.0, 59.0, 65.0, 72.0), ncaa_d1__M=(54.0, 59.0, 64.0, 70.0),
                  ncaa_d1__F=(40.0, 44.0, 48.0, 53.0), all=(45.0, 52.0, 58.0, 65.0)),
    benchmark_note="NCAA DI men 61–63 W/kg (Berberet 2024); ACB pros 57 W/kg.",
))
_add(TestSpec(
    "cmj_eccentric_rfd", "Eccentric braking RFD", "jump", "N/s", True,
    "Rate of force development during the braking phase of the countermovement jump.",
    "How fast the athlete can stop the dip and reverse it: the brake pedal of a change of "
    "direction, and a sensitive marker in knee rehab.",
    decimals=0, devices=("force_plate",),
    benchmarks=_b(all=(7000.0, 9500.0, 12000.0, 15000.0)),
    benchmark_note="NCAA DI men ~11,400 N/s; higher braking RFD separated high-minute players in one DI team.",
))
_add(TestSpec(
    "cmj_asymmetry", "Takeoff asymmetry", "jump", "%", False,
    "Left-right difference in concentric impulse on a dual force plate, as a percentage.",
    "Limbs pushing unevenly. Above 10–15% is worth a look; in a knee rehab it is a "
    "return-to-sport criterion.",
    decimals=1, devices=("force_plate",),
    benchmarks=_b(all=(15.0, 10.0, 6.0, 3.0)),
))
_add(TestSpec(
    "drop_jump_rsi", "Reactive strength index", "jump", "", True,
    "Drop from a 30 cm box, land and rebound as high and as fast as possible. RSI = flight "
    "time divided by ground contact time.",
    "Stiffness and reactive power: the quick second jump off the floor for a rebound.",
    decimals=2, devices=("force_plate", "jump_mat", "contact_grid"),
    benchmarks=_b(pro__M=(1.9, 2.3, 2.7, 3.1), ncaa_d1__M=(1.6, 2.0, 2.4, 2.8),
                  ncaa_d1__F=(1.2, 1.5, 1.8, 2.1), all=(1.4, 1.8, 2.2, 2.6)),
))
_add(TestSpec(
    "squat_jump", "Squat jump", "jump", "cm", True,
    "From a held 90° squat, jump with no countermovement. Force plate or jump mat.",
    "Pure concentric power. The gap between this and the countermovement jump is the "
    "stretch-shortening contribution.",
    decimals=1, devices=("force_plate", "jump_mat"),
    benchmarks=_b(ncaa_d1__M=(32.0, 36.0, 40.0, 44.0), ncaa_d1__F=(22.0, 25.0, 28.5, 32.0),
                  all=(26.0, 30.0, 35.0, 40.0)),
))
_add(TestSpec(
    "broad_jump", "Standing broad jump", "jump", "cm", True,
    "Two-foot takeoff and landing from a line; distance to the back of the nearest heel. Best "
    "of three.",
    "Horizontal power, the first step of a drive.",
    decimals=0, devices=("manual",),
    benchmarks=_b(pro__M=(265.0, 280.0, 295.0, 310.0), ncaa_d1__M=(245.0, 262.0, 278.0, 292.0),
                  ncaa_d1__F=(185.0, 200.0, 215.0, 230.0), high_school__M=(215.0, 235.0, 252.0, 268.0),
                  high_school__F=(160.0, 175.0, 190.0, 205.0), all=(200.0, 225.0, 250.0, 275.0)),
))
_add(TestSpec(
    "single_leg_cmj", "Single-leg jump", "jump", "cm", True,
    "Hands on hips, one-leg countermovement jump on the force plate (or the phone's "
    "flight-time test). Three per leg.",
    "Each leg on its own. The side-to-side difference is what matters, and it is a "
    "return-to-sport gate after a knee injury.",
    sided=True, decimals=1, devices=("force_plate", "phone"), phone=True, asymmetry_flag_pct=10.0,
    benchmarks=_b(ncaa_d1__M=(16.0, 19.0, 22.0, 25.0), ncaa_d1__F=(10.0, 12.5, 15.0, 18.0),
                  all=(12.0, 15.0, 18.0, 22.0)),
))
_add(TestSpec(
    "hop_single_distance", "Single hop for distance", "jump", "cm", True,
    "Stand on one leg, hop forward as far as possible and land on the same leg under control. "
    "Best of three per leg.",
    "The first of the four-hop battery. Limb symmetry index at or above 90% is the standard "
    "return-to-sport gate.",
    sided=True, decimals=0, devices=("manual", "phone"), asymmetry_flag_pct=10.0,
    benchmarks=_b(ncaa_d1__M=(170.0, 190.0, 210.0, 230.0), ncaa_d1__F=(130.0, 145.0, 160.0, 175.0),
                  all=(140.0, 160.0, 185.0, 210.0)),
))
_add(TestSpec(
    "cmj_depth", "Countermovement depth", "jump", "cm", True,
    "Peak downward displacement of the centre of mass in the countermovement jump.",
    "A strategy number, not a score: a changed dip with the same height is the athlete finding "
    "another way to jump, which is what fatigue and a sore knee both look like.",
    decimals=1, devices=("force_plate",),
    benchmarks=_b(all=(24.0, 28.0, 31.0, 34.0)),
    benchmark_note="NCAA DI men about 29–30 cm, women 27–29 cm (Berberet 2024, Philipp 2023).",
))
_add(TestSpec(
    "cmj_braking_impulse", "Braking net impulse", "jump", "N·s", True,
    "Net impulse through the braking phase of the countermovement jump.",
    "Eccentric capacity in one number; it is what a deceleration draws on.",
    decimals=0, devices=("force_plate",),
    benchmarks=_b(ncaa_d1__M=(100.0, 122.0, 140.0, 160.0), ncaa_d1__F=(90.0, 110.0, 128.0, 145.0),
                  all=(90.0, 115.0, 135.0, 155.0)),
))
_add(TestSpec(
    "cmj_impulse_ratio", "Impulse ratio", "jump", "", True,
    "Propulsive net impulse divided by braking net impulse in the countermovement jump.",
    "A range metric: about 2.1 to 2.2 is the collegiate norm. Drifting high means the athlete is "
    "braking less and pushing more; drifting low, the reverse.",
    decimals=2, devices=("force_plate",),
    benchmarks=_b(all=(1.85, 2.05, 2.20, 2.35)),
    benchmark_note="NCAA DI men 2.14–2.16 (95 % CI 2.07–2.24). Not a maximise-me metric.",
))
_add(TestSpec(
    "cmj_rebound_rsi", "Rebound jump RSI", "jump", "", True,
    "A maximal countermovement jump followed at once by a rebound jump; RSI of the rebound (flight "
    "time over contact time). The basketball-specific drop jump.",
    "Reactive strength off the floor from a real landing: the second jump for a rebound.",
    sports=("basketball",), decimals=2, devices=("force_plate",),
    benchmarks=_b(ncaa_d1__M=(1.70, 2.00, 2.30, 2.60), ncaa_d1__F=(1.20, 1.50, 1.80, 2.10),
                  all=(1.50, 1.85, 2.15, 2.45)),
    benchmark_note="NCAA DI men rebound RSI 2.07 guards / 1.99 forwards, contact ~290 ms (Berberet 2025).",
))
_add(TestSpec(
    "dsi", "Dynamic strength index", "strength", "", True,
    "Countermovement jump peak force divided by isometric mid-thigh pull peak force.",
    "Says what to train: below about 0.60 the athlete has power headroom and needs strength; above "
    "0.80 the strength is there and ballistic work pays.",
    decimals=2, devices=("force_plate",),
    benchmarks=_b(all=(0.55, 0.65, 0.75, 0.85)),
    benchmark_note="A coaching convention (0.60 / 0.80 cut points), not a norm; read it with the two tests it comes from.",
))
_add(TestSpec(
    "eccentric_utilization_ratio", "Eccentric utilisation ratio", "jump", "", True,
    "Countermovement jump height divided by squat jump height.",
    "How much the stretch-shortening cycle adds. Near 1.0, the countermovement is adding nothing "
    "and reactive work is the gap.",
    decimals=2, devices=("force_plate", "jump_mat"),
    benchmarks=_b(all=(1.02, 1.08, 1.14, 1.20)),
))
_add(TestSpec(
    "cod_deficit", "Change-of-direction deficit", "agility", "s", False,
    "505 time minus the 10 m sprint time, per side.",
    "How much the turn itself costs once straight speed is taken out; the fairer cutting number.",
    sided=True, decimals=2, devices=("timing_gates",), asymmetry_flag_pct=10.0,
    benchmarks=_b(all=(0.85, 0.70, 0.58, 0.48)),
))
_add(TestSpec(
    "sprint_5m", "5 m sprint", "speed", "s", False,
    "Standing start; split at 5 m.",
    "The first two steps.",
    decimals=2, devices=("timing_gates",),
    benchmarks=_b(pro__M=(1.10, 1.03, 0.97, 0.92), ncaa_d1__M=(1.14, 1.07, 1.01, 0.96),
                  ncaa_d1__F=(1.26, 1.18, 1.11, 1.05), all=(1.20, 1.12, 1.05, 0.98)),
))
_add(TestSpec(
    "rsa_mean_time", "Repeated sprint ability", "conditioning", "s", False,
    "10 × 15 m shuttles (30 m with a turn) every 30 s; the mean sprint time. Store the mean and total "
    "first: the fatigue index is the least reliable number in the test.",
    "Repeat-effort capacity on the court.",
    decimals=2, devices=("timing_gates", "manual"),
    benchmarks=_b(ncaa_d1__M=(6.20, 5.95, 5.75, 5.55), ncaa_d1__F=(6.90, 6.60, 6.35, 6.10),
                  all=(6.50, 6.20, 5.95, 5.70)),
))
_add(TestSpec(
    "orthostatic_hr_delta", "Orthostatic heart-rate response", "conditioning", "bpm", False,
    "Five minutes lying, then stand: heart rate at 90–120 s standing minus the lying rate.",
    "The autonomic test that still works in a very fit athlete whose HRV has saturated: a jump of "
    "more than 15–20 bpm above the athlete's own usual, or a blunted response, is a flag.",
    decimals=0, devices=("wearable", "phone", "chest_strap"), phone=True,
    benchmarks=_b(all=(24.0, 18.0, 14.0, 10.0)),
))

# --- speed --------------------------------------------------------------------------------

_add(TestSpec(
    "sprint_3q_court", "Three-quarter court sprint", "speed", "s", False,
    "From the baseline to the far free-throw line (75 ft / 22.9 m), timing gates or hand time. "
    "Best of two.",
    "The combine sprint: straight-line acceleration over the length of a fast break.",
    sports=("basketball",), decimals=2, devices=("timing_gates", "manual"), core=True,
    benchmarks=_b(pro__M=(3.40, 3.30, 3.20, 3.10), ncaa_d1__M=(3.50, 3.38, 3.28, 3.18),
                  ncaa_d1__F=(3.85, 3.72, 3.60, 3.48), high_school__M=(3.65, 3.52, 3.40, 3.28),
                  high_school__F=(4.05, 3.90, 3.76, 3.62), pro__F=(3.70, 3.58, 3.47, 3.36)),
    benchmark_note="NBA Draft Combine drafted-player mean 3.3 ± 0.1 s; the 2025 best was 2.97 s.",
))
_add(TestSpec(
    "sprint_10m", "10 m sprint", "speed", "s", False,
    "Standing start 0.5 m behind the first gate; split at 10 m. Best of three.",
    "First-step acceleration, the most trainable piece of speed.",
    decimals=2, devices=("timing_gates", "manual"), core=True,
    benchmarks=_b(pro__M=(1.78, 1.72, 1.66, 1.60), ncaa_d1__M=(1.84, 1.77, 1.71, 1.65),
                  ncaa_d1__F=(2.02, 1.95, 1.88, 1.82), all=(1.95, 1.85, 1.76, 1.68)),
))
_add(TestSpec(
    "sprint_20m", "20 m sprint", "speed", "s", False,
    "Standing start; split at 20 m through timing gates. Best of three.",
    "Acceleration into speed. The split between 10 and 20 m says whether the athlete keeps building.",
    decimals=2, devices=("timing_gates", "manual"), core=True,
    benchmarks=_b(pro__M=(3.05, 2.96, 2.88, 2.80), ncaa_d1__M=(3.15, 3.05, 2.96, 2.88),
                  ncaa_d1__F=(3.45, 3.35, 3.25, 3.15), all=(3.35, 3.20, 3.06, 2.94)),
))
_add(TestSpec(
    "sprint_30m", "30 m sprint", "speed", "s", False,
    "Standing start; split at 30 m. Best of three.",
    "The soccer sprint standard; the 20–30 m split is maximal velocity.",
    sports=("soccer", "tennis"), decimals=2, devices=("timing_gates",),
    benchmarks=_b(pro__M=(4.45, 4.30, 4.15, 4.02), ncaa_d1__M=(4.50, 4.35, 4.20, 4.08),
                  ncaa_d1__F=(4.95, 4.80, 4.66, 4.52), all=(4.70, 4.52, 4.36, 4.20)),
))
_add(TestSpec(
    "max_speed", "Max velocity", "speed", "km/h", True,
    "Peak speed from GPS/LPS in training or games, or over a 30–40 m fly.",
    "The athlete's top gear. Exposure to 90%+ of it every week is the hamstring's vaccine.",
    decimals=1, devices=("catapult", "kinexon", "statsports", "timing_gates"),
    benchmarks=_b(pro__M=(31.0, 32.5, 34.0, 35.5), ncaa_d1__M=(29.5, 31.0, 32.5, 34.0),
                  ncaa_d1__F=(26.0, 27.5, 29.0, 30.5), all=(27.0, 29.0, 31.0, 33.0)),
))

# --- agility & change of direction ---------------------------------------------------------

_add(TestSpec(
    "lane_agility", "Lane agility", "agility", "s", False,
    "Around the free-throw lane: sprint forward, slide left, backpedal, slide right, then the "
    "reverse. Timing gates at the start corner. Best of two.",
    "The combine agility drill: every defensive movement pattern in one loop.",
    sports=("basketball",), decimals=2, devices=("timing_gates", "manual"), core=True,
    benchmarks=_b(pro__M=(11.45, 11.10, 10.80, 10.50), ncaa_d1__M=(11.80, 11.40, 11.05, 10.75),
                  ncaa_d1__F=(13.10, 12.70, 12.30, 11.95), high_school__M=(12.40, 12.00, 11.65, 11.30),
                  high_school__F=(13.60, 13.20, 12.80, 12.40), pro__F=(12.60, 12.20, 11.85, 11.50)),
    benchmark_note="NBA Draft Combine drafted-player mean 11.1 ± 0.4 s; NCAA studies 10.2–11.8 s; the record is 9.93 s.",
))
_add(TestSpec(
    "shuttle_run_combine", "Shuttle run", "agility", "s", False,
    "The combine reactive shuttle: from the lane's centre, sprint to one side, touch, sprint to "
    "the other, touch, return. Best of two.",
    "Short change-of-direction speed, both directions.",
    sports=("basketball",), decimals=2, devices=("timing_gates", "manual"),
    benchmarks=_b(pro__M=(3.20, 3.02, 2.90, 2.78), ncaa_d1__M=(3.32, 3.15, 3.03, 2.92),
                  ncaa_d1__F=(3.65, 3.50, 3.38, 3.26), all=(3.40, 3.25, 3.12, 3.00)),
    benchmark_note="NBA Draft Combine drafted-player mean 3.0 ± 0.2 s; the 2025 best was 2.58 s.",
))
_add(TestSpec(
    "pro_agility_5_10_5", "Pro agility (5-10-5)", "agility", "s", False,
    "Start astride the middle line, sprint 5 yd, touch, 10 yd back, touch, 5 yd through. Timed "
    "from first movement. Both directions.",
    "The universal change-of-direction test; a left-right time gap is a cutting asymmetry.",
    decimals=2, devices=("timing_gates", "manual"), sided=True, asymmetry_flag_pct=6.0, core=True,
    benchmarks=_b(pro__M=(4.45, 4.32, 4.20, 4.08), ncaa_d1__M=(4.60, 4.45, 4.32, 4.20),
                  ncaa_d1__F=(5.05, 4.90, 4.75, 4.62), high_school__M=(4.85, 4.68, 4.52, 4.38),
                  high_school__F=(5.30, 5.12, 4.96, 4.80), all=(4.80, 4.60, 4.45, 4.30)),
))
_add(TestSpec(
    "t_test", "T-test", "agility", "s", False,
    "Sprint 10 yd, shuffle 5 yd left, 10 yd right, 5 yd back to centre, backpedal 10 yd.",
    "Shuffling and backpedaling at speed, the defensive stance under the clock.",
    decimals=2, devices=("timing_gates", "manual"),
    benchmarks=_b(ncaa_d1__M=(9.90, 9.50, 9.15, 8.85), ncaa_d1__F=(11.20, 10.70, 10.30, 9.90),
                  all=(10.60, 10.10, 9.60, 9.20)),
    benchmark_note="Collegiate basketball 8.9–9.8 s, pros 8.8–10.0 s (Morrison 2022).",
))
_add(TestSpec(
    "cod_505", "505 change of direction", "agility", "s", False,
    "Run through the 10 m gate, plant at the 15 m line on the named foot and return through "
    "the gate; timed over the last 5 m out and 5 m back. Both feet.",
    "The cleanest cut test: one plant, one foot. The side-to-side deficit is the number a "
    "knee rehab watches.",
    decimals=2, devices=("timing_gates",), sided=True, asymmetry_flag_pct=6.0,
    benchmarks=_b(pro__M=(2.45, 2.35, 2.27, 2.20), ncaa_d1__M=(2.55, 2.45, 2.36, 2.28),
                  ncaa_d1__F=(2.85, 2.72, 2.62, 2.52), all=(2.70, 2.55, 2.45, 2.35)),
))
_add(TestSpec(
    "reactive_agility", "Reactive agility", "agility", "s", False,
    "A Y-shaped cut where the direction is signalled by a light or a tester at the last moment. "
    "Smart-light timing (VALD SmartSpeed, Fitlight) or video.",
    "Decision plus movement: pre-planned agility measures the legs, this measures the game.",
    decimals=2, devices=("timing_gates",),
    benchmarks=_b(all=(2.10, 1.95, 1.85, 1.75)),
))
_add(TestSpec(
    "spider_test", "Spider test", "agility", "s", False,
    "From the centre mark, retrieve five balls placed at the corners and T of the singles court "
    "and return each to the centre. Timed.",
    "The tennis agility standard: court coverage and recovery footwork.",
    sports=("tennis",), decimals=2, devices=("manual",), core=True,
    benchmarks=_b(pro__M=(15.8, 15.2, 14.6, 14.0), ncaa_d1__M=(16.8, 16.1, 15.5, 14.9),
                  ncaa_d1__F=(18.4, 17.6, 16.9, 16.2), all=(18.0, 17.0, 16.0, 15.2)),
))
_add(TestSpec(
    "hexagon", "Hexagon", "agility", "s", False,
    "Two-foot hops out and back over each side of a 60 cm hexagon, three circuits, clockwise "
    "and anticlockwise.",
    "Foot speed and balance under fatigue. A direction gap is a sign to look at an ankle.",
    sports=("tennis",), decimals=2, devices=("manual",),
    benchmarks=_b(ncaa_d1__M=(12.2, 11.4, 10.8, 10.2), ncaa_d1__F=(13.6, 12.6, 11.9, 11.2),
                  all=(13.0, 12.0, 11.2, 10.5)),
))
_add(TestSpec(
    "arrowhead", "Arrowhead agility", "agility", "s", False,
    "Sprint 10 m, round the near cone, out to the point and back through the start. Both sides.",
    "The soccer change-of-direction battery test.",
    sports=("soccer",), decimals=2, devices=("timing_gates",), sided=True, asymmetry_flag_pct=5.0,
    benchmarks=_b(pro__M=(8.60, 8.35, 8.15, 7.95), ncaa_d1__M=(8.90, 8.60, 8.35, 8.15),
                  ncaa_d1__F=(9.80, 9.45, 9.15, 8.90), all=(9.30, 8.95, 8.65, 8.40)),
))

# --- strength -------------------------------------------------------------------------------

_add(TestSpec(
    "imtp_peak_force_rel", "Isometric mid-thigh pull", "strength", "N/kg", True,
    "Maximal isometric pull against a fixed bar at the mid-thigh position on a force plate; "
    "peak force relative to body mass. Two or three 3-second efforts.",
    "Whole-body maximal strength without a heavy barbell on the back: safe in season, and the "
    "base every jump and sprint number sits on.",
    decimals=1, devices=("force_plate",), core=True,
    benchmarks=_b(pro__M=(38.0, 42.0, 46.0, 51.0), ncaa_d1__M=(34.0, 38.0, 42.0, 47.0),
                  ncaa_d1__F=(27.0, 31.0, 35.0, 39.0), all=(30.0, 35.0, 40.0, 45.0)),
))
_add(TestSpec(
    "imtp_rfd_200", "IMTP RFD 0–200 ms", "strength", "N/s", True,
    "Rate of force development over the first 200 ms of the isometric mid-thigh pull.",
    "Explosive strength: force fast rather than force eventually.",
    decimals=0, devices=("force_plate",),
    benchmarks=_b(all=(6000.0, 8000.0, 10500.0, 13000.0)),
))
_add(TestSpec(
    "squat_1rm_rel", "Back squat (relative 1RM)", "strength", "× BW", True,
    "One-repetition maximum, or an estimate from a 3–5 RM set, divided by body mass.",
    "Lower-body strength per kilogram. Around 1.5× body mass is where jump and sprint gains "
    "from strength alone start to level off.",
    decimals=2, devices=("manual", "vbt"), core=True,
    benchmarks=_b(pro__M=(1.45, 1.65, 1.85, 2.05), ncaa_d1__M=(1.40, 1.60, 1.80, 2.00),
                  ncaa_d1__F=(1.00, 1.20, 1.40, 1.60), high_school__M=(1.10, 1.30, 1.50, 1.70),
                  all=(1.10, 1.35, 1.60, 1.85)),
    benchmark_note="NCAA DI men average about 1.6–1.7 × body mass (Creighton survey of 437 players).",
))
_add(TestSpec(
    "trap_bar_deadlift_rel", "Trap bar deadlift (relative)", "strength", "× BW", True,
    "One-repetition maximum (or estimated) on the trap bar, divided by body mass.",
    "The hinge-and-squat hybrid most basketball programs test instead of the back squat.",
    sports=("basketball", "soccer"), decimals=2, devices=("manual", "vbt"),
    benchmarks=_b(pro__M=(1.70, 1.95, 2.20, 2.45), ncaa_d1__M=(1.55, 1.80, 2.05, 2.30),
                  ncaa_d1__F=(1.20, 1.45, 1.65, 1.90), all=(1.40, 1.65, 1.90, 2.15)),
))
_add(TestSpec(
    "bench_press_185_reps", "Bench press, 185 lb reps", "strength", "reps", True,
    "Maximum repetitions at 185 lb (84 kg), full range, no pause.",
    "The combine upper-body test. Absolute, so bigs post higher numbers.",
    sports=("basketball",), decimals=0, devices=("manual",),
    benchmarks=_b(pro__M=(4.0, 8.0, 12.0, 16.0), ncaa_d1__M=(2.0, 5.0, 9.0, 13.0),
                  all=(2.0, 5.0, 9.0, 13.0)),
    benchmark_note="NBA Draft Combine; many wings skip it and are recorded as 0.",
))
_add(TestSpec(
    "bench_press_1rm_rel", "Bench press (relative 1RM)", "strength", "× BW", True,
    "One-repetition maximum (or estimated) divided by body mass.",
    "Upper-body pressing strength per kilogram.",
    decimals=2, devices=("manual", "vbt"),
    benchmarks=_b(ncaa_d1__M=(0.95, 1.10, 1.25, 1.40), ncaa_d1__F=(0.55, 0.68, 0.80, 0.92),
                  all=(0.75, 0.90, 1.05, 1.20)),
))
_add(TestSpec(
    "nordic_hamstring_force", "Nordic hamstring force", "strength", "N", True,
    "Kneeling on the NordBord, lower under control as far as possible; peak eccentric force "
    "per leg. Three reps.",
    "Eccentric hamstring strength is the hamstring-strain insurance policy. Below about 337 N "
    "and an asymmetry above 15% raise injury risk in team sport.",
    sided=True, decimals=0, devices=("nordbord", "dynamometer"), asymmetry_flag_pct=15.0, core=True,
    benchmarks=_b(pro__M=(300.0, 350.0, 400.0, 460.0), ncaa_d1__M=(280.0, 330.0, 380.0, 430.0),
                  ncaa_d1__F=(200.0, 240.0, 280.0, 320.0), all=(260.0, 310.0, 360.0, 410.0)),
    benchmark_note="Opar et al. 2015 (AFL): <337 N and >15% imbalance raised strain risk.",
))
_add(TestSpec(
    "hip_adduction_force", "Hip adduction (squeeze)", "strength", "N", True,
    "Supine, knees bent, squeeze the ForceFrame or dynamometer between the knees. Peak force, "
    "per side where the device separates them.",
    "Groin strength and the early-warning sign of groin trouble: a drop of 15% from baseline "
    "the morning after is the signal to pull back.",
    sided=True, decimals=0, devices=("forceframe", "dynamometer"), asymmetry_flag_pct=15.0,
    benchmarks=_b(pro__M=(330.0, 380.0, 430.0, 480.0), ncaa_d1__M=(300.0, 350.0, 400.0, 450.0),
                  ncaa_d1__F=(200.0, 240.0, 280.0, 320.0), all=(250.0, 300.0, 350.0, 400.0)),
))
_add(TestSpec(
    "hip_abduction_force", "Hip abduction", "strength", "N", True,
    "Supine against the ForceFrame or a handheld dynamometer; peak force per side.",
    "Lateral hip strength, the knee's chaperone in a cut and a landing.",
    sided=True, decimals=0, devices=("forceframe", "dynamometer"), asymmetry_flag_pct=15.0,
    benchmarks=_b(all=(220.0, 270.0, 320.0, 370.0)),
))
_add(TestSpec(
    "add_abd_ratio", "Adduction:abduction ratio", "strength", "", True,
    "Adduction peak force divided by abduction peak force, per side.",
    "Below about 0.8 the groin is under-powered against the hip and groin pain is more likely.",
    sided=True, decimals=2, devices=("forceframe", "dynamometer"),
    benchmarks=_b(all=(0.75, 0.85, 0.95, 1.05)),
))
_add(TestSpec(
    "knee_extension_iso", "Quad strength (isometric)", "strength", "N", True,
    "Seated, knee at 60–90°, maximal 3–5 s push against a fixed dynamometer (VALD DynaMo, "
    "Kinvent). Peak force per leg, three efforts.",
    "The number the knee rehab lives on. Limb symmetry index ≥ 90% is the return-to-sport "
    "standard; relative strength below ~3 N/kg is a reinjury risk.",
    sided=True, decimals=0, devices=("dynamometer", "isokinetic"), asymmetry_flag_pct=10.0,
    core=True,
    benchmarks=_b(pro__M=(600.0, 700.0, 800.0, 900.0), ncaa_d1__M=(520.0, 620.0, 720.0, 820.0),
                  ncaa_d1__F=(360.0, 430.0, 500.0, 570.0), all=(420.0, 520.0, 620.0, 720.0)),
))
_add(TestSpec(
    "knee_flexion_iso", "Hamstring strength (isometric)", "strength", "N", True,
    "Prone or seated, knee at 30°, maximal pull into the dynamometer. Peak force per leg.",
    "With quad strength, gives the hamstring:quad ratio; below 0.6 the hamstring is not "
    "protecting the knee.",
    sided=True, decimals=0, devices=("dynamometer", "isokinetic"), asymmetry_flag_pct=10.0,
    benchmarks=_b(all=(250.0, 320.0, 390.0, 460.0)),
))
_add(TestSpec(
    "calf_raise_reps", "Single-leg calf raise", "strength", "reps", True,
    "Standing on one leg on a step, full-range heel raises at one per two seconds to failure.",
    "Calf endurance: ankle and Achilles health, and the engine of the last step of a jump.",
    sided=True, decimals=0, devices=("manual",), asymmetry_flag_pct=15.0,
    benchmarks=_b(all=(20.0, 25.0, 30.0, 35.0)),
))
_add(TestSpec(
    "grip_strength", "Grip strength", "strength", "kg", True,
    "Hand dynamometer, elbow at 90°, maximal squeeze. Best of two per hand.",
    "A quick whole-body strength proxy; for tennis, the racquet arm's health.",
    sided=True, decimals=1, devices=("dynamometer",), asymmetry_flag_pct=15.0,
    benchmarks=_b(pro__M=(52.0, 58.0, 64.0, 70.0), ncaa_d1__M=(48.0, 54.0, 60.0, 66.0),
                  ncaa_d1__F=(30.0, 35.0, 40.0, 45.0), all=(38.0, 45.0, 52.0, 60.0)),
))
_add(TestSpec(
    "shoulder_er_ir_ratio", "Shoulder ER:IR strength", "strength", "", True,
    "External and internal rotation strength at 90° abduction with a handheld dynamometer; "
    "the ratio, dominant arm.",
    "Rotator cuff balance for a serving shoulder: below 0.66 the cuff is losing to the chest.",
    sports=("tennis",), sided=True, decimals=2, devices=("dynamometer",),
    benchmarks=_b(all=(0.60, 0.68, 0.75, 0.82)),
))
_add(TestSpec(
    "bar_velocity_squat", "Bar velocity at 80%", "strength", "m/s", True,
    "Mean concentric bar velocity on a back squat at 80% of 1RM, from a linear transducer "
    "(GymAware, Perch, Vitruve).",
    "Velocity at a fixed load tracks readiness and strength without maxing out in season.",
    decimals=2, devices=("vbt",),
    benchmarks=_b(all=(0.45, 0.52, 0.58, 0.65)),
))

# --- conditioning ---------------------------------------------------------------------------

_add(TestSpec(
    "yoyo_ir1", "Yo-Yo IR1", "conditioning", "m", True,
    "2 × 20 m shuttles at the beep with a 10 s jog between, speed rising each level, to the "
    "second miss. Distance covered.",
    "Intermittent endurance: the ability to repeat efforts. The test most basketball and "
    "soccer programs run in preseason.",
    decimals=0, devices=("manual", "timing_gates"), core=True,
    benchmarks=_b(pro__M=(1600.0, 1900.0, 2200.0, 2500.0), ncaa_d1__M=(1440.0, 1720.0, 2000.0, 2320.0),
                  ncaa_d1__F=(1040.0, 1240.0, 1440.0, 1680.0), high_school__M=(1200.0, 1440.0, 1720.0, 2000.0),
                  high_school__F=(880.0, 1040.0, 1240.0, 1440.0), pro__F=(1280.0, 1480.0, 1720.0, 1960.0)),
    benchmark_note="Pro basketball 1,120–2,389 m (Morrison 2022); soccer pros 1,350–2,520 m, so a soccer "
                   "athlete reads a level higher against these rows.",
))
_add(TestSpec(
    "yoyo_ir2", "Yo-Yo IR2", "conditioning", "m", True,
    "The faster version of the Yo-Yo: starts at 13 km/h, to the second miss. Distance.",
    "High-intensity intermittent capacity, the top end of the engine.",
    decimals=0, devices=("manual",),
    benchmarks=_b(pro__M=(880.0, 1040.0, 1200.0, 1400.0), ncaa_d1__M=(640.0, 800.0, 960.0, 1120.0),
                  ncaa_d1__F=(400.0, 520.0, 640.0, 760.0), all=(560.0, 720.0, 880.0, 1040.0)),
))
_add(TestSpec(
    "ift_30_15", "30-15 IFT (VIFT)", "conditioning", "km/h", True,
    "30 s shuttles with 15 s passive recovery, speed rising 0.5 km/h per stage, to failure. "
    "The final speed (VIFT).",
    "The intermittent fitness test whose result programs the conditioning: intervals are "
    "prescribed as percentages of VIFT.",
    decimals=1, devices=("manual",), core=True,
    benchmarks=_b(pro__M=(19.5, 20.5, 21.5, 22.5), ncaa_d1__M=(18.5, 19.5, 20.5, 21.5),
                  ncaa_d1__F=(16.5, 17.5, 18.5, 19.5), all=(17.5, 18.5, 19.5, 20.5)),
))
_add(TestSpec(
    "beep_test", "Multistage fitness test", "conditioning", "level", True,
    "The 20 m beep test, continuous, to the second miss. Final level and shuttle, as a decimal.",
    "A quick aerobic capacity estimate for a whole squad.",
    decimals=1, devices=("manual",),
    benchmarks=_b(ncaa_d1__M=(11.0, 12.0, 13.0, 14.0), ncaa_d1__F=(8.5, 9.5, 10.5, 11.5),
                  all=(9.5, 10.5, 11.8, 13.0)),
))
_add(TestSpec(
    "vo2_max", "VO₂ max", "conditioning", "mL/kg/min", True,
    "Lab treadmill test, or the watch's own estimate from outdoor runs.",
    "Aerobic ceiling. In basketball the floor for a starter is around 50; the recovery "
    "between efforts rides on it more than the efforts themselves.",
    decimals=1, devices=("lab", "wearable"),
    benchmarks=_b(pro__M=(52.0, 55.0, 58.0, 62.0), ncaa_d1__M=(49.0, 52.5, 56.0, 60.0),
                  ncaa_d1__F=(43.0, 46.5, 50.0, 54.0), all=(44.0, 49.0, 54.0, 59.0)),
))
_add(TestSpec(
    "repeated_sprint_decrement", "Repeated sprint decrement", "conditioning", "%", False,
    "6 × 30 m (or court-length) sprints on 20–25 s; decrement = total time over best time × 6, "
    "minus one, as a percentage.",
    "How much speed fades across repeated efforts: the fourth quarter in a number.",
    decimals=1, devices=("timing_gates", "manual"),
    benchmarks=_b(all=(8.0, 6.0, 4.5, 3.0)),
))
_add(TestSpec(
    "hr_recovery_1min", "Heart-rate recovery", "conditioning", "bpm", True,
    "The drop in heart rate one minute after a hard effort ends, from the watch or a chest strap.",
    "Parasympathetic reactivation: a recovery marker that improves with fitness and worsens "
    "with fatigue and illness.",
    decimals=0, devices=("wearable",),
    benchmarks=_b(all=(20.0, 28.0, 35.0, 42.0)),
))
_add(TestSpec(
    "suicides_17s", "17s (court suicides)", "conditioning", "s", False,
    "Seventeen sideline-to-sideline sprints as fast as possible; standard is under 60–65 s.",
    "The basketball conditioning rite: the team standard many programs set.",
    sports=("basketball",), decimals=1, devices=("manual",),
    benchmarks=_b(ncaa_d1__M=(66.0, 62.0, 59.0, 56.0), ncaa_d1__F=(74.0, 70.0, 66.0, 63.0),
                  all=(70.0, 65.0, 61.0, 58.0)),
))
_add(TestSpec(
    "shuttle_300yd", "300-yard shuttle", "conditioning", "s", False,
    "Six round trips of 25 yd, twice with a five-minute rest; mean of the two.",
    "Anaerobic capacity, the lactate test without the lactate.",
    decimals=1, devices=("manual", "timing_gates"),
    benchmarks=_b(ncaa_d1__M=(62.0, 59.0, 56.5, 54.0), ncaa_d1__F=(70.0, 66.0, 63.0, 60.0),
                  all=(66.0, 62.0, 59.0, 56.0)),
))

# --- mobility & balance ----------------------------------------------------------------------

_add(TestSpec(
    "ankle_dorsiflexion_ktw", "Ankle dorsiflexion (knee-to-wall)", "mobility", "cm", True,
    "Lunge the knee to the wall with the heel down; the furthest toe-to-wall distance at which "
    "the knee still touches. Per side.",
    "Below about 9–10 cm the ankle is stiff enough to send load up to the knee in a landing; "
    "a side-to-side gap over 2 cm is the ankle-sprain tell.",
    sided=True, decimals=1, devices=("manual", "phone"), phone=True, asymmetry_flag_pct=15.0, core=True,
    benchmarks=_b(all=(8.0, 10.0, 12.0, 14.0)),
))
_add(TestSpec(
    "y_balance_composite", "Y-balance composite", "mobility", "%", True,
    "Single-leg stance, reach anterior, posteromedial and posterolateral; composite = sum of "
    "the three reaches over three times leg length, as a percentage. Per side.",
    "Dynamic balance and control. Below 94% and an anterior reach difference over 4 cm "
    "between sides are injury-risk markers in team sport.",
    sided=True, decimals=1, devices=("manual",), asymmetry_flag_pct=8.0,
    benchmarks=_b(all=(88.0, 94.0, 99.0, 104.0)),
))
_add(TestSpec(
    "y_balance_anterior", "Y-balance anterior reach", "mobility", "cm", True,
    "The anterior reach of the Y-balance test, per side.",
    "The reach direction most sensitive to ankle and knee restriction; the side gap is the number.",
    sided=True, decimals=1, devices=("manual",), asymmetry_flag_pct=6.0,
    benchmarks=_b(all=(55.0, 62.0, 68.0, 74.0)),
))
_add(TestSpec(
    "single_leg_balance", "Single-leg balance (eyes closed)", "mobility", "s", True,
    "Stand on one leg with eyes closed and hands on hips; time to a touch-down or hop, up to 60 s. "
    "Per side. The phone measures sway when held at the chest.",
    "Proprioception after an ankle sprain and a cheap concussion baseline.",
    sided=True, decimals=0, devices=("manual", "phone"), phone=True, asymmetry_flag_pct=25.0,
    benchmarks=_b(all=(15.0, 25.0, 40.0, 60.0)),
))
_add(TestSpec(
    "hip_internal_rotation", "Hip internal rotation", "mobility", "°", True,
    "Seated or prone, knee at 90°, rotate the lower leg outward; the angle, per side.",
    "Hip rotation is the first thing a stiff lower back or groin steals.",
    sided=True, decimals=0, devices=("manual", "phone"), phone=True, asymmetry_flag_pct=15.0,
    benchmarks=_b(all=(25.0, 32.0, 40.0, 47.0)),
))
_add(TestSpec(
    "hamstring_ake", "Hamstring flexibility (active knee extension)", "mobility", "°", True,
    "Supine, hip at 90°, actively straighten the knee; degrees short of full extension, per side.",
    "Hamstring length. A deficit over 20° or a side gap is a strain and back risk.",
    sided=True, decimals=0, devices=("manual", "phone"), phone=True, asymmetry_flag_pct=20.0,
    benchmarks=_b(all=(30.0, 20.0, 12.0, 5.0)),
))
_add(TestSpec(
    "shoulder_ir_rom", "Shoulder internal rotation", "mobility", "°", True,
    "Supine, arm at 90° abduction, rotate the forearm toward the floor; the angle, per side.",
    "A dominant-side deficit over 18–20° (GIRD) is the serving shoulder's warning sign.",
    sports=("tennis",), sided=True, decimals=0, devices=("manual", "phone"), phone=True,
    asymmetry_flag_pct=20.0,
    benchmarks=_b(all=(40.0, 50.0, 60.0, 70.0)),
))
_add(TestSpec(
    "shoulder_total_arc", "Shoulder total arc of motion", "mobility", "°", True,
    "Internal plus external rotation at 90° abduction, per side.",
    "A total arc more than 5° short on the dominant side is a shoulder injury risk for overhead athletes.",
    sports=("tennis",), sided=True, decimals=0, devices=("manual", "phone"), asymmetry_flag_pct=5.0,
    benchmarks=_b(all=(150.0, 165.0, 178.0, 190.0)),
))
_add(TestSpec(
    "fms_total", "Functional Movement Screen", "mobility", "/21", True,
    "Seven movement patterns scored 0–3 by a certified tester.",
    "A movement-quality screen. Below 14 is the published injury-risk cut, with the usual caveats.",
    decimals=0, devices=("manual",),
    benchmarks=_b(all=(13.0, 15.0, 17.0, 19.0)),
))
_add(TestSpec(
    "less_score", "Landing error score (LESS)", "mobility", "errors", False,
    "Drop from a 30 cm box to a line half body height away and jump; two video angles scored "
    "for 17 landing errors.",
    "Landing mechanics on video: six or more errors flags knee-injury risk; the thing an ACL "
    "prevention program trains.",
    decimals=0, devices=("video", "phone"),
    benchmarks=_b(all=(7.0, 5.0, 4.0, 2.0)),
))

# --- body --------------------------------------------------------------------------------------

_add(TestSpec(
    "body_mass", "Body mass", "body", "kg", True,
    "Morning, after the bathroom, before food, same scale.",
    "The daily weigh-in is also a hydration test: more than 2% down from the morning norm is "
    "dehydration carried into practice.",
    decimals=1, devices=("scale", "withings", "inbody"), core=True,
))
_add(TestSpec(
    "body_fat_pct", "Body fat", "body", "%", False,
    "DXA, InBody or a seven-site skinfold by the same tester each time.",
    "Composition, in the athlete's own trend. Position and sex set the range; the trend sets the plan.",
    decimals=1, devices=("dxa", "inbody", "skinfold"), core=True,
    benchmark_note="Methods are not interchangeable: DXA reads several points higher than skinfolds or BIA. "
                   "NBA Draft Combine 6.7 ± 1.9 %; meta-analysis of 4,335 players: men 13.2 %, women 20.4 %.",
    benchmarks=_b(pro__M=(10.5, 8.5, 7.0, 5.8), ncaa_d1__M=(13.5, 11.0, 9.0, 7.5),
                  ncaa_d1__F=(26.0, 22.5, 19.5, 17.0), high_school__M=(15.0, 12.5, 10.5, 9.0),
                  all=(16.0, 13.0, 11.0, 9.0)),
))
_add(TestSpec(
    "lean_mass", "Lean mass", "body", "kg", True,
    "Fat-free mass from DXA or InBody.",
    "What the training is building. Tracked in season to catch the slow loss a long schedule causes.",
    decimals=1, devices=("dxa", "inbody"),
))
_add(TestSpec(
    "height", "Height", "body", "cm", True, "Barefoot, stadiometer.", "Recorded once a season.",
    decimals=1, devices=("manual",),
))
_add(TestSpec(
    "wingspan", "Wingspan", "body", "cm", True, "Fingertip to fingertip, arms level.",
    "The combine anthropometric that matters most for a defender's reach.",
    sports=("basketball",), decimals=1, devices=("manual",),
))
_add(TestSpec(
    "standing_reach", "Standing reach", "body", "cm", True,
    "Flat-footed, one arm fully extended overhead.",
    "The base every vertical is measured from, and a rim-protection number in itself.",
    sports=("basketball",), decimals=1, devices=("manual",),
))
_add(TestSpec(
    "hand_length", "Hand length", "body", "cm", True, "Wrist crease to the tip of the middle finger.",
    "Ball control; a combine measurement.", sports=("basketball",), decimals=1, devices=("manual",),
))
_add(TestSpec(
    "hand_width", "Hand width", "body", "cm", True, "Thumb tip to little-finger tip, hand spread.",
    "A combine measurement.", sports=("basketball",), decimals=1, devices=("manual",),
))

# --- skill ------------------------------------------------------------------------------------

_add(TestSpec(
    "shooting_pct_3pt", "Three-point percentage", "skill", "%", True,
    "Made over attempted in a standard spot-shooting session (e.g. 100 shots, five spots), from "
    "a shot tracker or by hand.",
    "Practice shooting against the athlete's own trend; a dip beside a readiness dip is the "
    "link between sleep and the shot.",
    sports=("basketball",), decimals=1, devices=("noah", "shottracker", "homecourt", "manual"),
    benchmarks=_b(all=(33.0, 38.0, 43.0, 48.0)),
))
_add(TestSpec(
    "free_throw_pct", "Free-throw percentage", "skill", "%", True,
    "Made over attempted in a block of free throws.",
    "The closed-skill number. Sensitive to fatigue and sleep more than people expect.",
    sports=("basketball",), decimals=1, devices=("noah", "shottracker", "manual"),
    benchmarks=_b(all=(68.0, 75.0, 81.0, 87.0)),
))
_add(TestSpec(
    "serve_speed", "Serve speed", "skill", "km/h", True,
    "First-serve speed from a radar gun or court system, best of ten.",
    "The tennis power number; a drop with a sore shoulder is the first thing to check.",
    sports=("tennis",), decimals=0, devices=("radar", "playsight", "manual"), core=True,
    benchmarks=_b(pro__M=(185.0, 198.0, 210.0, 222.0), ncaa_d1__M=(160.0, 172.0, 184.0, 196.0),
                  ncaa_d1__F=(140.0, 150.0, 160.0, 170.0), pro__F=(160.0, 172.0, 182.0, 192.0),
                  all=(140.0, 155.0, 170.0, 185.0)),
))
_add(TestSpec(
    "medball_overhead_throw", "Overhead med ball throw", "skill", "m", True,
    "3 kg (men) or 2 kg (women) ball, backward overhead throw for distance. Best of three.",
    "Whole-body power through the kinetic chain, the serve without the racquet.",
    sports=("tennis",), decimals=1, devices=("manual",),
    benchmarks=_b(ncaa_d1__M=(12.0, 13.5, 15.0, 16.5), ncaa_d1__F=(8.5, 10.0, 11.5, 13.0),
                  all=(10.0, 11.5, 13.0, 15.0)),
))
_add(TestSpec(
    "medball_rotational_throw", "Rotational med ball throw", "skill", "m", True,
    "Side-on, 3 kg ball, hip-to-shoulder rotational throw for distance; forehand and backhand sides.",
    "Rotational power, the groundstroke engine. The side gap is a trunk asymmetry.",
    sports=("tennis",), sided=True, decimals=1, devices=("manual",), asymmetry_flag_pct=10.0,
    benchmarks=_b(ncaa_d1__M=(11.0, 12.5, 14.0, 15.5), ncaa_d1__F=(8.0, 9.5, 11.0, 12.5),
                  all=(9.0, 10.5, 12.0, 13.5)),
))
_add(TestSpec(
    "reaction_time", "Reaction time", "skill", "ms", False,
    "The phone's tap test: tap when the screen changes, ten trials, the median.",
    "Simple reaction time slows with sleep loss and after a head knock; the cheapest daily "
    "cognitive readiness check there is.",
    decimals=0, devices=("phone",), phone=True,
    benchmarks=_b(all=(280.0, 250.0, 225.0, 200.0)),
))

# --- views ----------------------------------------------------------------------------------------


def tests_for(sport: str, *, core_only: bool = False) -> list[TestSpec]:
    out = [t for t in TESTS.values() if not t.sports or sport in t.sports]
    if core_only:
        out = [t for t in out if t.core]
    order = {c["key"]: i for i, c in enumerate(CATEGORIES)}
    return sorted(out, key=lambda t: (order.get(t.category, 99), not t.core, t.label))


def benchmark_for(spec: TestSpec, level: str | None, sex: str | None) -> tuple[tuple[float, float, float, float] | None, str]:
    """The closest reference row and a label for where it came from."""
    if not spec.benchmarks:
        return None, ""
    s = (sex or "").upper()[:1]
    if s not in ("M", "F"):
        s = "M"
    lvl = level or "ncaa_d1"
    # Levels without their own table borrow the nearest one.
    ladder = {
        "pro": ["pro", "ncaa_d1"], "ncaa_d1": ["ncaa_d1", "pro"], "ncaa_d2": ["ncaa_d1"],
        "ncaa_d3": ["ncaa_d1", "high_school"], "juco": ["ncaa_d1", "high_school"],
        "high_school": ["high_school", "ncaa_d1"], "club": ["ncaa_d1", "high_school"],
        "recreational": ["high_school", "ncaa_d1"],
    }
    for candidate in ladder.get(lvl, ["ncaa_d1"]):
        row = spec.benchmarks.get(f"{candidate}:{s}")
        if row:
            return row, f"{candidate}:{s}"
    row = spec.benchmarks.get("all")
    return (row, "all") if row else (None, "")


def band_for(spec: TestSpec, value: float, level: str | None, sex: str | None) -> dict[str, Any] | None:
    """Where this value sits against the level: a 0–100 position and a word."""
    row, ref = benchmark_for(spec, level, sex)
    if row is None:
        return None
    p25, p50, p75, p90 = row
    anchors = [(p25, 25.0), (p50, 50.0), (p75, 75.0), (p90, 90.0)]
    if not spec.higher_is_better:
        # Lower is better: the row is written best-last, so flip the axis.
        anchors = [(-v, p) for v, p in anchors]
        value = -value
    # Piecewise-linear percentile, extrapolated gently beyond the ends.
    pct: float
    if value <= anchors[0][0]:
        span = max(anchors[1][0] - anchors[0][0], 1e-9)
        pct = max(2.0, 25.0 - 25.0 * (anchors[0][0] - value) / span)
    elif value >= anchors[-1][0]:
        span = max(anchors[-1][0] - anchors[-2][0], 1e-9)
        pct = min(99.0, 90.0 + 10.0 * (value - anchors[-1][0]) / span)
    else:
        pct = 50.0
        for (v0, p0), (v1, p1) in zip(anchors, anchors[1:]):
            if v0 <= value <= v1:
                pct = p0 + (p1 - p0) * (value - v0) / max(v1 - v0, 1e-9)
                break
    word = ("Elite" if pct >= 90 else "Strong" if pct >= 75 else "Solid" if pct >= 50
            else "Developing" if pct >= 25 else "Below level")
    return {"percentile": round(pct), "word": word, "reference": ref,
            "p25": p25, "p50": p50, "p75": p75, "p90": p90}


def test_view(spec: TestSpec) -> dict[str, Any]:
    return {
        "key": spec.key, "label": spec.label, "category": spec.category, "unit": spec.unit,
        "higher_is_better": spec.higher_is_better, "protocol": spec.protocol, "why": spec.why,
        "sports": list(spec.sports), "sided": spec.sided, "decimals": spec.decimals,
        "devices": list(spec.devices), "phone": spec.phone,
        "asymmetry_flag_pct": spec.asymmetry_flag_pct, "core": spec.core,
        "benchmark_note": spec.benchmark_note,
    }
