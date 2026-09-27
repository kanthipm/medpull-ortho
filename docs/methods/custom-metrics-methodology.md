---
title: "MedPull in-house metrics: inputs, functions and methodology"
subtitle: "Engine version mobility-1 · for scientific review"
date: "2026-09-26"
---

# MedPull in-house metrics: inputs, functions and methodology

**Engine version** `mobility-1` · **Code** `backend/app/engine/mobility/` · **Status** implemented, verified on synthetic signals, **not yet clinically validated** · **Prepared** 2026-09-26 for external scientific review.

## 1. Purpose and scope

MedPull monitors patients after orthopaedic surgery from the data their phone and wearable produce. Until this version the gait metrics on the clinician's dashboard were Apple's (walking speed, step length, asymmetry, double support, steadiness, stair speeds, six-minute walk), which exist on no other platform, are closed algorithms, and are partly weakly validated (Apple's own double-support ICC 0.53; asymmetry validated only as a classifier on 51 healthy adults in knee braces). No vendor exposes range of motion or a stress score comparable across devices.

This document specifies the metrics MedPull now computes **itself**, with one algorithm for every patient regardless of the phone or wearable they own. For each metric it lists the inputs, the function that produces it, the constants, the assumptions, what has been verified, and what has not. It is written so that a reviewer can check every step against the code, which is short, pure numpy, and organised one module per section below.

**What is in-house and what is not.** The table classifies the twenty statistics the product tracks.

| Statistic | Source on the dashboard | Notes |
|---|---|---|
| Steps, exercise sessions, sleep, sleep stages, heart rate, HRV, respiratory rate, SpO<sub>2</sub>, skin temperature, calories | Wearable vendor via Junction, or Apple Health via the app | Vendor-measured; shown with vendor provenance. HRV is RMSSD on most devices, SDNN on Apple; the two are never mixed in one series. |
| Stress index | **In-house** (§12) | Derived daily from the vendor's HRV, resting HR and respiratory rate against the patient's own baseline. |
| Walking speed, step length, cadence | **In-house** (§7) | From the phone's IMU; Apple's values are kept as a second row for comparison. |
| Walking asymmetry, double support | **In-house** (§6) | Thigh-gyroscope phase model. |
| Walking steadiness | **In-house** (§8) | Explicit gait-variability index; Apple's classifier is closed. |
| Stair ascent / descent speed | **In-house** (§9) | Barometer + steps. |
| Six-minute walk distance | **In-house** (§10) | An active in-app test. |
| Range of motion (flexion, extension, abduction) | **In-house** (§11) | Phone-inclinometer protocol. |

When both an in-house row and a vendor row exist for the same metric on the same day, the day's value on the dashboard is the in-house one; the vendor row remains visible in the raw data (§13).

## 2. Data acquisition: the phone as the common sensor

No consumer wearable exposes raw inertial data through its API. The phone does, and every patient has one, so the phone is the sensor for everything in §3–§11. The patient app records a **motion window** during a guided walk (3 min), a six-minute walk test, or a range-of-motion test, and uploads it; the server computes every metric. Nothing is computed on the phone, which is what keeps iPhone and Android on one algorithm.

**Window contents** (`MotionWindow`, `frames.py`):

| Field | Unit / shape | Source (iOS) | Required |
|---|---|---|---|
| `accel` | m/s², N×3, device frame, gravity included | device motion: user acceleration + gravity, × 9.80665 | yes |
| `gyro` | rad/s, N×3 | device motion: rotation rate | no (asymmetry falls back, double support absent) |
| `gravity` | unit vector, N×3 | device motion: gravity estimate | no (estimated by a 0.25 Hz low-pass otherwise) |
| `timestamps` | s from start, N | device motion: timestamp | no (nominal rate trusted otherwise) |
| `altitude` | [s, m] pairs | altimeter: relative altitude | no (stairs need it) |
| pedometer steps and distance | count, m | pedometer | no |
| GPS distance and accuracy | m | location manager, fixes with horizontal accuracy ≤ 20 m only | no (outdoor walks) |
| `height_cm` | cm | the Health app's height sample, or entered once | needed for step length and speed |
| `pocket_side` | left / right | asked on screen | no (labels the instrumented leg) |

Nominal sampling is 50 Hz; a window is capped at 12 minutes (36,000 samples). Carriage is a **front trouser pocket, top end up** — the placement Apple's iPhone metrics also assume — so the phone rides on the thigh. Every derived row records the window's context, the number of steps behind it, the method, and quality flags in `value_json`, so a reviewer can audit any single number back to its bout.

**Sign conventions.** iOS reports the gravity vector pointing into the ground and Android out of it. Every quantity below that reads the vertical acceleration is sign-invariant (integration range, autocorrelation, harmonic ratio, spectral power); the convention is recorded, never relied upon.

## 3. Preprocessing (`frames.py`, `dsp.py`)

1. **Resampling.** With per-sample timestamps the window is linearly interpolated onto a uniform 50 Hz grid; duplicate stamps are dropped.
2. **Gravity direction** `g_hat(t)`: the phone's estimate, normalised; else the 0.25 Hz low-passed acceleration, normalised.
3. **Two scalar signals**, both mean-removed over the window:
   - `a_mag = |a| − mean|a|` — orientation-free; used for bout and step detection.
   - `a_vert = a·g_hat − mean(a·g_hat)` — the dynamic component along gravity; used for step length and the steadiness features.
4. **Filters.** All filters are second-order Butterworth biquads (RBJ cookbook coefficients, Q = 1/√2) applied forward and backward (`filtfilt`) over a reflected edge pad, giving a zero-phase fourth-order response. Zero phase matters: a filter must not move a heel strike in time. Peak finding, autocorrelation, the Hann-windowed rFFT and the trapezoidal integrator are implemented in `dsp.py` (≈150 lines) so nothing depends on scipy.

## 4. Walking bouts (`bouts.py`)

A 2 s window slides over `a_mag` with a 1 s hop. A window is *walking* when all three hold: (i) the 0.5–6 Hz band-passed signal has SD > **0.35 m/s²**; (ii) the dominant frequency lies in the step band **0.8–3.2 Hz** (48–192 steps/min, slow frame-assisted walking included); (iii) at least **30 %** of spectral power lies in that band. Walking windows are merged across gaps ≤ **2 s**; a bout shorter than **10 s** is discarded. *Rationale*: Mobilise-D's real-world validation shows per-bout speed error falling sharply once a bout holds ~10 strides (Kirk 2024).

## 5. Steps and temporal parameters (`steps.py`)

Steps are peaks of the 0.5–3.5 Hz band-passed `a_mag`, one per foot contact whichever way the phone sits. Peaks closer than **0.30 s** collapse to the taller. The amplitude threshold is **0.35 × median of the upper half** of candidate peak heights — a pocketed phone feels the near leg's contact harder than the far leg's, and this keeps the quieter contralateral contacts while dropping noise.

From step instants `t_i`:

- step time `Δt_i = t_{i+1} − t_i`; cadence `= 60 / mean(Δt)` [steps/min];
- stride time `= Δt_i + Δt_{i+1}`;
- step-time CV `= SD(Δt) / mean(Δt)`.

A bout is accepted only if it has ≥ **8** steps, cadence within **40–200** spm, and step-time CV ≤ **0.40**.

## 6. Gait phases: asymmetry and double support (`phases.py`)

The thigh's angular velocity about the mediolateral axis over one stride (Aminian 2002 for the shank; the thigh form is standard in exoskeleton phase detection):

| Event | Thigh angular velocity |
|---|---|
| Heel strike (HS) | peak flexion: crosses from positive to **negative** |
| Stance | extending: negative lobe |
| ~50 % of cycle | reversal (peak extension): crosses back to positive, ≈ the other foot's heel strike |
| Toe-off (TO) | the steepest rise of the flexion lobe (the leg unloads) |
| Swing | the large positive lobe, ending at the next HS |

**Procedure.** (1) The sagittal axis is the principal component of the gyroscope over the bout; the sign is chosen so the faster (swing) lobe is positive. (2) The signal is low-passed at **6 Hz**; swing peaks are found (≥ 0.5 s apart, ≥ 0.5 × median height). (3) For each swing peak: HS = next negative-going zero crossing; reversal c = previous positive-going zero crossing; TO = argmax of dω/dt between c and the peak. (4) Stride `T_k = HS_k − HS_{k−1}`; swing `W_k = HS_k − TO_k`.

**Which foot is which.** Rather than trusting the reversal crossing (which sits in a flat, noisy region), the accelerometer's foot contacts from §5 are **labelled**: a contact within **0.15 s** of a thigh heel strike belongs to the instrumented leg, the rest to the other leg. Both legs' step times therefore come from one detector. The labelling must assign 30–70 % of contacts to the instrumented leg or the bout falls back to the unlabelled estimate.

**Outputs.**

- Step-time asymmetry index `SI = (mean Δt_ipsi − mean Δt_contra) / mean(Δt) × 100` [%] (Robinson's symmetry index, signed positive when the instrumented leg's step is slower). Stored as |SI| with the signed value and the pocket side in `value_json`, so the console can name the leg.
- Double support `DS = 100 × (1 − 2 W / T)` [%]. Derivation: both feet are on the ground except during each swing, so single support per stride is `W_ipsi + W_contra`; assuming the contralateral swing equals the measured one, `DS = T − 2W`. Healthy walking (W/T ≈ 0.40) gives ≈ 20 %, the textbook figure.
- Validity: ≥ 4 strides and mean swing fraction within 0.20–0.60.

**Without a gyroscope** (an old or restricted phone) asymmetry is the unsigned index over alternating accelerometer step times (`alternating_asymmetry`) and double support is not computed.

**Limitations stated.** (a) The contralateral swing is not measured; an asymmetric patient's double support carries the instrumented side's bias — the same limitation Apple documents for the iPhone. Recording the pocket side and alternating it brackets the truth. (b) Toe-off from the steepest rise of the flexion lobe is a rule adopted from the thigh-IMU literature, not a fitted model; its timing error against force plates is the first thing a validation should measure. (c) Double support from a single thigh sensor is the weakest metric in this document, as it is for Apple (ICC 0.53) and in the pocket-phone literature (Larsen 2025: 30–73 % error); it is displayed on bands (§12) and never enters the risk tier.

## 7. Step length and walking speed (`spatial.py`)

**Model.** Zijlstra & Hof (2003): during single support the centre of mass follows an arc over the stance leg, so the vertical excursion `h` within a step and the leg length `l` give

`SL = K · 2 · √(2 l h − h²)`

with `l = 0.53 × stature` (Winter's anthropometrics, greater trochanter height) and `K = 1.25` (Zijlstra's empirical correction for the parts of the step the pendulum does not describe).

**Vertical excursion.** `a_vert` is low-passed at **5 Hz** (the centre of mass has no meaningful content above it; the heel-strike transient the thigh feels does), high-passed at **0.1 Hz**, integrated (trapezoid) to velocity, high-passed again, integrated to displacement, high-passed again; `h` is max − min of the displacement between consecutive foot contacts, clipped to **0.005–0.12 m**. Per-step lengths are clipped to **0.10–1.60 m**.

**Bout estimate.** The first and last **2** strides sit in the integrators' edge transient and are dropped when enough remain; the bout's step length is the **median** of the rest; distance = median × number of intervals; speed = distance / bout duration (≡ step length × cadence / 60).

**GPS calibration.** When a window carries a GPS distance with mean horizontal accuracy ≤ **12 m** and the bout has ≥ **40** steps and is the whole walk, `K_cal = GPS distance / uncorrected distance` (clipped to 0.6–2.0) replaces the default and the row is flagged `calibrated: true`. This is the personalisation Soltani et al. (2020) showed halves wrist speed error. Until a patient has a calibrated K the default applies and the row says so.

**Placement caveat.** Zijlstra validated with a lower-trunk sensor; a pocketed phone rides on the thigh. The thigh's vertical excursion is close to, not identical to, the trunk's, and heel-strike transients are larger. K therefore needs its own pocket-carriage calibration (validation plan, §15). Without stature and without GPS no step length or speed is produced; with GPS alone, speed is GPS distance / duration.

## 8. Walking-steadiness index (`stability.py`)

An explicit, fixed combination of four features the prospective fall-risk literature has repeatedly found informative on trunk or pocket accelerometry (Hausdorff 2001; Weiss 2013; Rispens 2015; van Schooten 2016), computed per bout on `a_vert` low-passed at 10 Hz:

| Feature | Definition | Anchor (score 0.5) | Scale | Better | Weight |
|---|---|---|---|---|---|
| step-time CV | §5 | 0.045 | 0.015 | lower | 0.30 |
| stride regularity | normalised unbiased autocorrelation at the stride lag | 0.65 | 0.12 | higher | 0.20 |
| harmonic ratio | Σ amplitudes at even harmonics of the stride frequency / Σ at odd harmonics (Menz 2003), 20 harmonics | 1.7 | 0.4 | higher | 0.20 |
| walking speed | §7 (omitted when unavailable; weights renormalise) | 0.85 m/s | 0.15 | higher | 0.30 |

Each feature maps to 0–1 by a logistic `1 / (1 + e^{−d (x − anchor)/scale})` (d = ±1), and the index is `100 × Σ w_i f_i / Σ w_i`. Bands mirror Apple's three levels: **≥ 60 OK, 40–60 Low, < 40 Very low**.

**What the index is not.** A validated fall-risk classifier. The features are reimplemented from the literature; the anchors are the values those studies report separating typical from impaired community-dwelling older adults; the weights are a defensible starting point. The dashboard labels the card *guarded* and reads it on the bands, not on a control chart against the pre-op norm (every post-operative patient is less steady than before surgery).

## 9. Stair ascent and descent speed (`stairs.py`)

The altitude trace is resampled to 2 Hz, median-filtered (3 samples) and low-passed at 0.3 Hz; the vertical velocity is its gradient. A run of samples with |v| > **0.08 m/s** in one direction (gaps ≤ 2 s bridged) is a candidate flight when its height change is ≥ **2.5 m** (one domestic flight; Apple uses ~3 m). Because smoothing stretches a flight's edges symmetrically, the duration is taken between the **10 % and 90 %** crossings of the height change, and

`speed = 0.8 × |Δh| / (t90 − t10)` [m/s, vertical]

A flight is kept only if it holds ≥ **6** detected steps (§5) — what separates stairs from an elevator — and 0.10 ≤ speed ≤ 1.50 m/s. One row per flight, ascent and descent separately.

## 10. Six-minute walk (`active.py`)

The supervised test (ATS 2002) walks a marked corridor for six minutes; distance is the outcome. The in-app test times six minutes and estimates distance from the best evidence the phone has, in this order:

1. **GPS** path length, when mean horizontal accuracy ≤ 12 m (outdoors; Salvi 2020: bias ≈ −1 m, limits of agreement ≈ ±37 m against a trundle wheel);
2. the phone's **pedometer distance** (Apple calibrates it per user from GPS walks; indoors it is the best single estimate);
3. steps × mean step length from §7 over the IMU recorded during the test;
4. steps × 0.415 × stature, the classical heuristic, as a last resort.

A test stopped early is scaled to six minutes (capped at 1.5×) and flagged. Reported with it: the method, the step count, cadence, per-minute step counts and the **endurance fade** `(minute 6 − minute 1) / minute 1 × 100`. Apple's passive weekly estimate is not reproduced: it needs population-scale training data.

## 11. Range of motion (`active.py`)

**Protocol.** Chew et al. (2024, PLOS One; n = 30 primary TKA, median age 66): the phone's long edge rests on the limb segment and its tilt is read from the gravity vector; MAD 4.5° flexion (ICC 0.97) and 2.2° extension (ICC 0.98) against extendable-arm goniometry; every patient could perform it unaided. The app records a 2 s **reference** hold and a 2 s **movement** hold.

**Function.** Tilt of the phone's long axis from horizontal in its own sagittal plane, over the full range so a 120° knee is not folded to 60°:

`tilt = atan2(−g_y, −g_z)` [deg]; `angle = |median(tilt_movement) − median(tilt_reference)|`

with the phone's top end toward the joint and the screen up in the reference position. Extension keeps the sign (positive = residual flexion, negative = hyperextension). A hold whose tilt SD exceeds **3°** is flagged unsteady.

| Protocol | Reference hold | Movement hold | Series |
|---|---|---|---|
| knee_flexion_supine | leg straight on the bed, phone on the shin | heel slid to maximum flexion | `rom_flexion` |
| knee_extension_supine | phone flat on the bed | knee pressed to maximum extension, heel propped | `rom_extension` |
| hip_flexion_supine | thigh flat, phone on the thigh | knee toward the chest | `rom_flexion` |
| shoulder_flexion_standing / shoulder_abduction_standing | arm hanging, phone on the upper arm | arm raised forward / sideways | `rom_flexion` / `rom_abduction` |

Each movement is its own series (joint and side travel on the row) so a 110° flexion and a 5° extension deficit never average into one number.

## 12. Stress index (`stress.py`)

No vendor exposes a comparable stress score (Garmin and Oura ship proprietary ones; Apple, Fitbit, WHOOP and Samsung ship none), so the index is computed the same way for every device from daily summaries.

- Inputs: `ln(HRV)` (RMSSD, or SDNN when that is what the device ships — whichever series exists, never both), resting heart rate, sleep respiratory rate.
- Baseline per input: the trailing **42 days** ending the day before, at least **3** values (a phone-synced wearable reports in clusters, not nightly); mean and SD with physiological SD floors (0.15 in ln-units, because day-to-day RMSSD varies by 10–20 % in healthy adults, Plews 2013; 1.5 bpm; 0.6 breaths/min) so one quiet week cannot make a normal night look extreme.
- Strain z: `−z(ln HRV)`, `+z(RHR)`, `+z(RR)`, each clipped to ±3.
- Composite: weighted mean over the inputs present that day (HRV 0.4, RHR 0.4, RR 0.2, renormalised).
- `index = clip(50 + 25 × composite, 0, 100)`: **50 = at the patient's own baseline, 75 = one SD of strain.**

The construction follows the HRV–stress literature (RMSSD and HF power fall, heart rate rises under sympathetic load: Kim 2018 meta-analysis) and Firstbeat's stress/recovery framing without its proprietary model. Baevsky's stress index needs beat-to-beat intervals, which daily summaries do not carry; it is the natural extension once the app uploads `HKHeartbeatSeries`. Dashboard bands: **≥ 75 flag, 62.5–75 watch**; until seven baseline days exist the card is labelled an early estimate and is capped at watch.

## 13. From rows to the clinician's dashboard

- **Rows.** One `INTERVAL` observation per bout per metric (walking speed, step length, cadence, asymmetry, double support, steadiness), one per flight (stair speeds), one `SESSION` per six-minute walk, one `INSTANT` per joint test, plus the walk itself as an exercise session with per-minute cadence and speed (which the guided-walk task verification and the walking-economy / endurance-fade care metrics read). Provider `medpull`, device `medpull:imu:<model>`. Rows are deterministic and idempotent: a retried upload lands on the same rows.
- **Daily series.** The engine's daily value is the mean of the day's bouts. When a day has both a MedPull row and a vendor row for the same metric, only MedPull's enters the series; the vendor row stays in the raw data for side-by-side comparison.
- **Comparison.** Activity-shaped metrics (step length, cadence, stair speeds, six-minute walk, exercise minutes, active energy) are judged, like steps and walking speed already were, against the procedure's expected-recovery curve as a fraction of the patient's own reference — every post-operative patient walks shorter and slower than before surgery, and that is not a finding. Joint angles are judged against the patient's own early readings (a loss of motion is the finding). Steadiness, double support, asymmetry and stress read on absolute bands. Tests taken every few days (six-minute walk, joint angles) keep a longer recency window (14 and 10 days) before a card calls them stale. Every metric in the panel is always a card: one never measured says so and names what would fill it; one with history but nothing current shows its last reading and date; a sparkline keeps the last two weeks or the last eight readings, whichever is longer.
- **Risk tier.** None of the in-house metrics feeds the risk tier, the multi-signal composite or the trajectory index. They are charted and judged for the clinician; the tier's inputs are unchanged until the validation in §15 supports adding them.

## 14. Verification performed

Every algorithm is exercised in `backend/tests/test_mobility.py` (22 tests) on synthetic pocket-phone signals with known ground truth (`tests/synth_motion.py`: a cosine centre-of-mass arc whose excursion is the pendulum inverse of the chosen step length; zero-net-impulse heel-strike transients, the near leg's harder; a thigh angular-velocity waveform with a slow reversal, the steepest rise a quarter into the flexion lobe, and a sharp deceleration into heel strike; optional stairs; sensor noise). Observed on those signals:

| Quantity | Truth range tested | Recovered | 
|---|---|---|
| step count | 80–124 steps / 60 s | within 3 |
| cadence | 80–125 spm | within 1 spm |
| step length (uncalibrated, K = 1.25) | 0.45–0.75 m | −0.3 % to +8.5 % |
| walking speed | 0.60–1.56 m/s | same as step length |
| step-time asymmetry (signed) | −10.5 %, 0 %, +14 % | within 4 points, correct sign |
| double support | 19.8–28.9 % | within 5 points |
| stair speed | 0.375 up, 0.429 down m/s | within 0.06 m/s; elevator rejected |
| joint angle | 7°, −4°, 95°, 120° | within 1.5°; unsteady hold flagged |
| stress index | flat baseline, then HRV −12 ms and RHR +6 bpm | 40–60 on baseline, ≥ 75 on average under strain |

These are self-consistency checks of the rules, not evidence about patients.

## 15. Validation plan and open questions (for the reviewer)

1. **Gait (§4–§7) against an instrumented walkway or APDM/Mobilise-D reference**, pocket phone, in the target population (TKA/THA, 60–80 y, weeks 1–12, with and without a frame or cane). Outcomes: bias and 95 % limits of agreement, ICC(2,1), and the minimal detectable change (MDC<sub>95</sub> = 1.96 × √2 × SEM) per metric, because the engine's SD floors (`baseline.py`) are currently literature-derived placeholders that the MDCs should replace. n ≈ 30–40 gives ICC confidence intervals of ±0.15. Specific questions: the toe-off rule's timing error (§6); the pocket-carriage K and whether a single population K or per-patient GPS calibration is needed (§7); the double-support bias with the phone on the operated vs the non-operated side.
2. **Steadiness (§8)**: cross-sectional association with the Timed Up-and-Go, gait speed and fall history, then prospective falls at 6 months. The weights and anchors should be refit; the bands should then be set on the fitted score.
3. **Six-minute walk (§10)** against the supervised corridor test in the same session (outdoor GPS and indoor pedometer arms separately).
4. **Range of motion (§11)**: replicate Chew 2024 for the knee with MedPull's two-hold protocol and extend to the shoulder protocols, which have no published smartphone-inclinometer validation.
5. **Stress index (§12)**: convergent validity against a validated self-report (e.g. PSS-4 daily) and against pain scores; specificity to post-operative complications is an outcome question for the risk engine, not this index.
6. **Known limitations to weigh**: single-thigh phase model (§6); K placement (§7); no passive free-living capture yet (windows are recorded during app-guided walks, because iOS does not deliver raw motion to a backgrounded app without a location mode); Apple-vs-MedPull agreement can be measured for free from the paired rows the system already stores.

## 16. References

- Aminian K, et al. Spatio-temporal parameters of gait measured by an ambulatory system using miniature gyroscopes. *J Biomech* 2002;35:689–699.
- ATS Committee. ATS statement: guidelines for the six-minute walk test. *Am J Respir Crit Care Med* 2002;166:111–117.
- Chew et al. Smartphone-based knee range-of-motion self-measurement after total knee arthroplasty. *PLOS One* 2024. PMC11449355.
- Fary C, et al. Recovery of walking metrics after TKA on a smartphone platform (mymobility). *Sensors* 2023. PMC10305196.
- Hausdorff JM, Rios DA, Edelberg HK. Gait variability and fall risk in community-living older adults. *Arch Phys Med Rehabil* 2001;82:1050–1056.
- Kim HG, et al. Stress and heart rate variability: a meta-analysis. *Psychiatry Investig* 2018;15:235–245.
- Kirk C, et al. Mobilise-D insights to estimate real-world walking speed in multiple conditions with a wearable device. *Sci Rep* 2024;14:1754.
- Larsen et al. Pocket-phone gait phase estimation. *Sensors* 2025. PMC12299727.
- Menz HB, Lord SR, Fitzpatrick RC. Acceleration patterns of the head and pelvis when walking on level and irregular surfaces. *Gait Posture* 2003;18:35–46.
- Micó-Amigo ME, et al. Assessing real-world gait with digital technology? Validation, insights and recommendations from the Mobilise-D consortium. *J NeuroEng Rehabil* 2023;20:78.
- Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M. Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring. *Sports Med* 2013;43:773–781.
- Rispens SM, et al. Identification of fall risk predictors in daily life measurements: gait characteristics' reliability and association with self-reported fall history. *Neurorehabil Neural Repair* 2015;29:54–61.
- Salvi D, et al. App-based versus standard six-minute walk test in pulmonary hypertension. *JMIR mHealth uHealth* 2020;8:e13756.
- Soltani A, et al. Real-world gait speed estimation using wrist sensor: a personalized approach. *IEEE J Biomed Health Inform* 2020;24:658–668.
- van Schooten KS, et al. Daily-life gait quality as predictor of falls in older people. *PLOS One* 2016;11:e0158623.
- Weiss A, et al. Does the evaluation of gait quality during daily life provide insight into fall risk? *Neurorehabil Neural Repair* 2013;27:742–752.
- Werner C, et al. Concurrent validity of Apple's iPhone mobility metrics against an instrumented walkway. *Sci Rep* 2023. PMC10067003.
- Winter DA. *Biomechanics and Motor Control of Human Movement*, 4th ed. Wiley 2009 (anthropometric segment lengths).
- Zijlstra W, Hof AL. Assessment of spatio-temporal gait parameters from trunk accelerations during human walking. *Gait Posture* 2003;18:1–10.
- Apple. *Measuring Walking Quality Through iPhone Mobility Metrics* (2021, rev. 2022); *Using Apple Watch to Estimate Six-Minute Walk Distance* (2021).

## Appendix A. Parameter table

| Constant | Value | Where | Meaning |
|---|---|---|---|
| FS | 50 Hz | frames.py | working sample rate |
| GRAVITY_LP_HZ | 0.25 Hz | frames.py | gravity estimate when the phone sends none |
| WINDOW_S / HOP_S | 2 s / 1 s | bouts.py | bout detector window |
| MIN_STD | 0.35 m/s² | bouts.py | minimum band-passed SD for walking |
| STEP_BAND | 0.8–3.2 Hz | bouts.py | step-frequency band |
| MIN_BAND_RATIO | 0.30 | bouts.py | share of power in the step band |
| MERGE_GAP_S / MIN_BOUT_S | 2 s / 10 s | bouts.py | bout merging and minimum length |
| MIN_STEP_S | 0.30 s | steps.py | minimum interval between contacts |
| HEIGHT_FRACTION | 0.35 | steps.py | contact threshold (× median of the upper half of peaks) |
| MIN_STEPS / CADENCE_RANGE / MAX_CV | 8 / 40–200 spm / 0.40 | steps.py | bout acceptance |
| GYRO_LP_HZ | 6 Hz | phases.py | thigh angular-velocity smoothing |
| MIN_SWING_PEAK_S / PEAK_FRACTION | 0.5 s / 0.5 | phases.py | swing peak detection |
| LABEL_TOLERANCE_S | 0.15 s | phases.py | contact-to-heel-strike labelling window |
| MIN_STRIDES / SWING_FRACTION_RANGE | 4 / 0.20–0.60 | phases.py | phase validity |
| LEG_LENGTH_RATIO / K_DEFAULT | 0.53 / 1.25 | spatial.py | pendulum geometry and correction |
| COM_LP_HZ / DRIFT_HP_HZ | 5 Hz / 0.1 Hz | spatial.py | integration filters |
| H_RANGE / SL_RANGE | 0.005–0.12 m / 0.10–1.60 m | spatial.py | plausibility clips |
| EDGE_TRIM | 2 strides | spatial.py | edge transient exclusion |
| GPS_MAX_ACCURACY_M / GPS_MIN_STEPS / K_RANGE | 12 m / 40 / 0.6–2.0 | spatial.py | GPS calibration gate |
| ANCHORS / WEIGHTS / LOW / VERY_LOW | §8 table / 60 / 40 | stability.py | steadiness index |
| ALT_FS / FLIGHT_MIN_M / MIN_V / V_RANGE / MIN_STEPS | 2 Hz / 2.5 m / 0.08 m/s / 0.10–1.50 m/s / 6 | stairs.py | stair detection |
| GPS_MAX_ACCURACY_M / STEP_LENGTH_HEIGHT_RATIO / HOLD_MAX_SD | 12 m / 0.415 / 3° | active.py | six-minute walk and ROM |
| BASELINE_DAYS / MIN_BASELINE_DAYS / WEIGHTS / SD_FLOORS / Z_CLIP | 42 / 3 / 0.4-0.4-0.2 / 0.15-1.5-0.6 / 3 | stress.py | stress index |
| STRESS_FIRM_DAYS | 7 | metrics_cards.py | baseline days before the stress band may flag |
| STRESS_FLAG / STRESS_WATCH | 75 / 62.5 | metrics_cards.py | dashboard bands |
| STEADINESS_LOW / VERY_LOW | 60 / 40 | metrics_cards.py | dashboard bands |
| DOUBLE_SUPPORT_OK / FLAG | 28 % / 40 % (after post-op day 10) | metrics_cards.py | dashboard bands |
| GAIT_FLAG_PCT | 10 % (after post-op day 10) | risk.py | asymmetry rule (unchanged) |

## Appendix B. API contracts

`POST /api/mobile/observations/motion` — `{windows: [MotionWindow…] (≤ 12), height_cm?, device_model?}`; `MotionWindow = {started_at, sample_rate_hz, accel[N][3], gyro?[N][3], gravity?[N][3], timestamps?[N], altitude?[M][2], gps_distance_m?, gps_accuracy_m?, pedometer_steps?, pedometer_distance_m?, pocket_side?, context}`. Returns per-window summaries and ingest counts.

`POST /api/mobile/tests/six-minute-walk` — `{started_at, duration_s, steps?, pedometer_distance_m?, gps_distance_m?, gps_accuracy_m?, minute_steps?, height_cm?, motion?}`. Returns distance, method, cadence, fade.

`POST /api/mobile/tests/range-of-motion` — `{recorded_at, protocol, side, reference[K][3], movement[K][3]}`. Returns joint, movement, angle, steadiness of the holds.

All three run every row through the same ingest path as a wearable delivery (plausibility bounds, the surgery window, idempotent dedupe) and recompute the patient's assessment immediately.
