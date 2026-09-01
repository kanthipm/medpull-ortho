# Real-world measurement validity of consumer wearables in slow, impaired, post-surgical gait (Apple Watch, Fitbit, Garmin, Oura, Whoop, Samsung), including Apple Mobility metrics and FDA status

## Summary

The single most consequential finding for Recovery Copilot: wrist-worn step counting collapses exactly in the population we monitor. A 2026 PeerJ study (n=42, ages 51-80) measured Apple Watch Series 8 at -36.4% step undercount during a 6-minute walk with a rolling walker (Omron waist pedometer: +4.3%), and -16.3% at 1.61 km/h (0.45 m/s) treadmill walking. A 2025 IJERPH brief report found Fitbit Inspire 3 at the wrist had 31.2% error pushing a two-wheeled walker versus 1.5% at hip/ankle and only -1.9% with a cane. The CADENCE program reports slow-speed MAPE of ~50% versus ~16% at normal speeds, and wrist ~23% versus waist/thigh ~4%. This means raw daily step deltas in weeks 0-3 post-TKA/THA are dominated by device artifact (arm on a walker = no arm swing), not by physiology, and any recovery curve fit to them will read a walker-to-cane transition as a spurious step surge. Apple's Mobility metrics are a better instrument but come from the iPhone, not the Watch: Apple's own validation (n=179 validation cohort, mean age 74.7, pressure-mat reference) gives walking speed ICC 0.92 with σ_error 0.15 m/s and median MDC 0.14 m/s, step length ICC 0.84, but double support time only ICC 0.53 - and the "slow" condition validated was 1.04 ± 0.18 m/s, i.e. Apple never validated below ~0.8 m/s, and only <5% of the cohort used assistive devices. Independent validation vs APDM Mobility Lab (2023, n=83) reproduces this pattern (gait speed ICC 0.85-0.86, double support ICC 0.42-0.58). Vitals fare better: nocturnal RHR bias is under 1.5 bpm and RMSSD MAPE 6-16% across Oura/Whoop/Garmin/Polar, but each vendor samples HRV over a different window (Oura 5-min windows averaged over sleep; Whoop weighted to the last slow-wave episode; Polar only the first 4 h), so cross-device baselines are not interchangeable. Sleep staging is weak everywhere (kappa 0.21-0.53; wake specificity 29-52%). SpO2 US availability has a hard regulatory discontinuity (removed Jan 2024, restored Aug 14 2025 with computation moved to iPhone). Nothing we would use for RTM - steps, distance, SpO2, HRV, temperature, sleep stages, walking steadiness, VO2max, Mobility metrics - is FDA-cleared; all are general wellness.

## Findings

### Apple Watch undercounts steps by 36.4% when the patient pushes a rolling walker
*[strong]*

PeerJ (April 15, 2026; PMID 42004701), 42 community-dwelling adults (23M/19F, aged 51-80, mean 60.6 ± 5.8). Devices: Apple Watch Series 8 (wrist) and Omron Walking Style IV (waist) vs a manual tally counter as reference. Conditions: unassisted, forearm crutch, rolling walker, oxygen trolley; treadmill at 1.61 / 3.22 / 4.83 km/h plus a 6MWT. Rolling-walker 6MWT: Apple Watch -36.4% (p=.001) vs Omron +4.3% (p=.021). Pooled across all conditions the Apple Watch ran a median -39.5 steps low while the Omron ran +11.0 ± 28.3 steps high. This is the closest published analogue to a week-1 post-TKA patient.

> Why your smartwatch may be misleading your doctor: a cross-sectional study on the impact of mobility aids on wearable accuracy in older adults, PeerJ 2026 — https://pmc.ncbi.nlm.nih.gov/articles/PMC13091583/

### Wrist step error is speed-dependent and inverts vs waist devices below ~0.5 m/s
*[strong]*

Same PeerJ 2026 cohort, treadmill: at 1.61 km/h (0.45 m/s) Apple Watch -16.3% and Omron -44.8%; at 3.22 km/h (0.89 m/s) Apple Watch -0.1% and Omron +3.9%; at 4.83 km/h (1.34 m/s) Apple Watch -6.9% and Omron -1.4%. So the Watch's error is not monotonic - it is near-zero at ~0.9 m/s, degrades below it, and degrades again at fast speed. Any correction factor must be a function of estimated cadence/speed, not a constant.

> PeerJ 2026 (PMID 42004701) — https://pmc.ncbi.nlm.nih.gov/articles/PMC13091583/

### Fitbit at the wrist: 31.2% error with a walker vs 1.5% at hip/ankle; a cane is nearly harmless
*[strong]*

Int J Environ Res Public Health 22(7):1100, published 12 July 2025. Fitbit Inspire 3 worn simultaneously at wrist, hip and ankle (bilaterally), n=11 healthy adults (mean age 24.9 ± 7.9, 63% male), video analysis as gold standard. Percent error: no device 0.1% (all positions); single-point cane -1.9% (all positions); two-wheeled rolling walker 1.5% at hip/ankle but 31.2% at the wrist. Key operational implication: the assistive-device effect is specific to walkers/rollators (both hands fixed to the frame), not to canes, so 'uses an assistive device' is too coarse a flag - we need device type.

> The Effect of Assistive Devices on the Accuracy of Fitbits in Healthy Individuals: A Brief Report, IJERPH 2025 — https://pmc.ncbi.nlm.nih.gov/articles/PMC12294748/

### CADENCE program: slow-speed step MAPE ~50%, and wrist placement is ~6x worse than waist
*[moderate]*

CADENCE-Kids (Int J Behav Nutr Phys Act 2021, 10.1186/s12966-021-01167-y) and CADENCE-Adults (PMC9461139) treadmill catalogs: across wearables, MAPE = 50.1 ± 35.5% at slow speeds (0.8-3.2 km/h band) versus 15.9 ± 21.7% at normal speeds. By wear location at normal speed: waist 4%, thigh 4%, ankle 5%, wrist 23%. Five research devices (Actical, waist ActiGraph GT3X+, activPAL, StepWatch, SW-200) achieved <5% MAPE across normal speeds; no wrist consumer device did. Note these are treadmill, directly-observed-step studies in able-bodied participants - real impaired gait is worse.

> CADENCE-Kids, IJBNPA 2021 — https://ijbnpa.biomedcentral.com/articles/10.1186/s12966-021-01167-y ; CADENCE-Adults — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9461139/

### Apple's own step validation never went below 1.04 m/s and used the iPhone, not the Watch
*[strong]*

Apple 'Measuring Walking Quality Through iPhone Mobility Metrics' (May 2022). Reference: ProtoKinetics Zeno Walkway 8 m pressure mat on a 12 m course. Pressure-mat reference means for Cohort A: slow speed 1.04 ± 0.18 m/s (range 0.47-1.57), cadence 101.6 ± 10.5 spm, step length 0.61 ± 0.08 m, double support 31.37 ± 3.69%; self-selected 1.30 ± 0.18 m/s; 6MWT 1.46 ± 0.18 m/s. iPhone pedometer vs mat: r² = 0.98 (slow, n_dv=845), 0.98 (self-selected, n_dv=854), 0.99 (6MWT, n_dv=738). Critically, the 'slow' condition mean is 1.04 m/s - well above the <0.8 m/s regime of early post-op recovery - and only 13/359 (5%) of the design cohort used assistive devices (<10, <5% in validation). Apple explicitly states the metrics 'will need to be further validated for more specific populations'.

> Apple, Measuring Walking Quality Through iPhone Mobility Metrics, May 2022 — https://www.apple.com/healthcare/docs/site/Measuring_Walking_Quality_Through_iPhone_Mobility_Metrics.pdf

### Apple Walking Speed: ICC 0.92, σ_error 0.15 m/s, median MDC 0.14 m/s — MDC exceeds the clinical MCID
*[strong]*

Apple white paper Table 4, validation set: N=250 participant-visits (179 unique participants, age 74.7 ± 5.3, 80% with musculoskeletal conditions, 49% osteoarthritis, 16% prior joint replacement), 7,440 walkovers. Validity σ_error = 0.15 m/s (design 0.09); reliability ICC(A,1) = 0.92 (design 0.93); minimal detectable change 0.08 m/s (10th pct) / 0.14 (50th) / 0.23 (90th). Computation: derived from a center-of-mass model, so accuracy requires the iPhone to be closely coupled to the body (pocket near hip or belt) and the user's current height entered in the Health app; no calibration. The commonly cited fall-risk signal is a 10 cm/s (0.10 m/s) decline per year — below the median MDC, so single-day walking-speed changes are not trustworthy; only multi-day aggregates are.

> Apple Mobility Metrics white paper, May 2022, Table 4 — https://www.apple.com/healthcare/docs/site/Measuring_Walking_Quality_Through_iPhone_Mobility_Metrics.pdf

### Apple Step Length is usable (ICC 0.84) but Double Support Time is not (ICC 0.53)
*[strong]*

Apple white paper Tables 5 and 6, validation set (N=250 visits, 7,440 walkovers). Step length: σ_error 0.05 m, ICC(A,1) 0.84 (design 0.85), r²=0.85, MDC 0.04/0.07/0.12 m. Double support time: σ_error 2.95%, ICC(A,1) 0.53 (design 0.59), r²=0.57 (design 0.65), MDC 2.06-4.51 percentage points. Double support is the metric most directly tied to post-op guarding and fear of falling, and it is the least reliable one Apple ships. Typical range 20-40% of gait cycle, lower = better balance.

> Apple Mobility Metrics white paper, May 2022, Tables 5-6 — https://www.apple.com/healthcare/docs/site/Measuring_Walking_Quality_Through_iPhone_Mobility_Metrics.pdf

### Apple Walking Asymmetry is a classifier trained on a knee brace, not on real post-surgical gait
*[strong]*

Apple white paper Figure 8 / Table 7. Asymmetry is reported as % of steps in a bout detected as asymmetric (0-100%). Reference: overall temporal symmetry ratio SSR = (swing/stance)*100, symmetry = max(SSR_L,SSR_R)/min(SSR_L,SSR_R); bins symmetry 1.0-1.1, mild 1.1-1.5, severe >1.5 (2,478 / 516 / 94 device-visits). At an iPhone-asymmetry threshold of 35%, positive predictive rate 83.4% (348 true positives of 417 asymmetry-classified device-visits) and false-negative rate 9.8% (262 of 2,671). Cohort B, which produced the asymmetry design data, was n=51 young adults (age 37.5 ± 7.3) wearing a knee brace locked to 30° flexion / 10° extension to simulate injury. Apple concedes the mechanics 'could differ substantially' from real pathology. This is the metric most tempting for a TKA/ACL cohort and the weakest-evidenced one.

> Apple Mobility Metrics white paper, May 2022, Fig 8 / Table 7 / Discussion — https://www.apple.com/healthcare/docs/site/Measuring_Walking_Quality_Through_iPhone_Mobility_Metrics.pdf

### Independent (non-Apple) validation vs APDM Mobility Lab reproduces the ranking and confirms double support is poor
*[strong]*

PMC10067003, 2023: 83 participants across three age groups (27 children 12-17, 28 adults 18-64, 28 seniors >=65). Reference: APDM Mobility Lab with Opal IMUs on both feet and L5. iPhone in right front pants pocket, display facing participant. Concurrent-validity ICC vs APDM — gait speed: children 0.86 (0.70-0.94), adults 0.86 (0.70-0.94), seniors 0.85 (0.61-0.94). Step length: children 0.53 (0.18-0.76), adults 0.78 (0.34-0.92), seniors 0.76 (0.32-0.90). Double support time: children 0.54 (0.09-0.80), adults 0.58 (0.25-0.79), seniors 0.42 (0.02-0.70). One-week test-retest in seniors: gait speed 0.88, step length 0.93, double support 0.91. Conclusion: valid for gait speed and step length in adults/seniors; caution for double support at all ages.

> Validity and reliability of the Apple Health app on iPhone for measuring gait parameters in children, adults, and seniors, 2023 — https://pmc.ncbi.nlm.nih.gov/articles/PMC10067003/

### Apple Mobility metrics are prefiltered and sparse — you cannot assume daily coverage
*[strong]*

Apple white paper Discussion + Figure 9: Mobility metrics are reported in HealthKit only during flat overground walking. They are explicitly NOT produced while running, hiking uphill, or on stairs, and are unavailable entirely if Wheelchair mode is enabled in the Health app. Availability depends on carry location — a pocket near the hip yields far more estimates than hand/backpack/purse. Apple's own figure: of users who receive at least one walking-bout estimate, on average >80% receive at least five Mobility estimates per day. That leaves a meaningful minority with 1-4 estimates/day, and it is silent about the housebound early-post-op patient who may not carry a phone while walking to the bathroom. Pedometer step counts and Mobility metric windows do not overlap.

> Apple Mobility Metrics white paper, May 2022, Discussion / Fig 9 — https://www.apple.com/healthcare/docs/site/Measuring_Walking_Quality_Through_iPhone_Mobility_Metrics.pdf

### Real post-arthroplasty HealthKit values: gait speed hovers ~0.96-0.99 m/s and steady-state steps are ~3,500-5,000/day
*[strong]*

J Arthroplasty / Arthroplasty Today 2025 (PMC12398885; PubMed 40893391), Rothman Institute. 209 enrolled (152 TKA, 57 THA), propensity-matched to 55 TKA vs 55 THA, Apple Watch + HealthKit, weekly averages at preop, 6 weeks, 6 and 12 months. Walking Steadiness (0-1): TKA 0.61 preop -> 0.49 at 6 months -> 0.66 at 12 months; THA 0.57 -> 0.63 -> 0.84 (between-group p=.031 at 6 mo, p=.044 at 12 mo). Step count: TKA 3,755 preop -> 4,261 at 12 mo; THA 3,571 -> 5,039 (p=.075). Gait speed: both 0.97 m/s preop; TKA 0.96 and THA 0.99 at 12 months (p=.263). Two things matter for us: (a) gait speed barely moves across a year, so it is a poor short-horizon recovery signal, whereas steadiness separates procedures; (b) the authors state they did NOT formally validate reliability of the HealthKit measurements and note variable device adherence.

> Improved Walking Steadiness Following Total Hip Arthroplasty Compared to Total Knee Arthroplasty, 2025 — https://pmc.ncbi.nlm.nih.gov/articles/PMC12398885/

### Nocturnal RHR is accurate to ~1-1.4 bpm; RMSSD MAPE ranges 6.0% (Oura 4) to 16.3% (Polar)
*[strong]*

Physiological Reports 2025 (PMC12367097), 13 adults (7M/6F, 33.2 ± 8.6 y), 536 nights, reference Polar H10 single-lead ECG at 1000 Hz. Nocturnal RHR — Oura Gen3: bias -0.88 ± 1.00 bpm, LOA -2.84 to 1.08, MAPE 1.67 ± 1.54%, CCC 0.97 (470 nights); Oura Gen4: -0.94 ± 1.43, LOA -3.75 to 1.87, MAPE 1.94%, CCC 0.98 (138 nights); Polar Grit X Pro: -0.01 ± 2.13, MAPE 2.71%, CCC 0.86; WHOOP 4.0: -1.41 ± 1.69, LOA -4.72 to 1.90, MAPE 3.00%, CCC 0.91. HRV (RMSSD) — Oura Gen4: bias -0.96 ± 5.52 ms, LOA -11.78 to 9.85, MAPE 5.96%, CCC 0.99; Oura Gen3: -2.50 ± 4.56 ms, MAPE 7.15%, CCC 0.97; WHOOP 4.0: -0.78 ± 5.98 ms, MAPE 8.17%, CCC 0.94; Garmin Fenix 6: -1.84 ± 6.86 ms, LOA -15.22 to 11.60, MAPE 10.52%, CCC 0.87; Polar Grit X Pro: -4.65 ± 9.67 ms, MAPE 16.32 ± 24.39%, CCC 0.82. Note the LOA width: ±11-15 ms on RMSSD is large relative to the deviations our CUSUM chart is chasing.

> Validation of nocturnal resting heart rate and heart rate variability in consumer wearables, Physiological Reports 2025 — https://pmc.ncbi.nlm.nih.gov/articles/PMC12367097/

### Every vendor computes HRV over a different window — RMSSD values are not cross-device comparable
*[strong]*

Same Physiological Reports 2025 paper documents the sampling contracts: Oura Gen3/Gen4 sample PPG at 250 Hz and compute RMSSD in 5-minute windows averaged across the entire sleep period; WHOOP 4.0 samples at 52 Hz and 'dynamically weights toward the last slow-wave sleep stage'; Garmin Fenix 6 uses undisclosed PPG frequency with 5-min windows averaged over detected sleep; Polar Grit X Pro samples at 1 Hz and restricts calculation to the first 4 hours after sleep onset. Garmin was excluded outright from the RHR analysis because its 'lowest 30-min average in a 24 h period' has undisclosed timestamp semantics. Apple, by contrast, samples HRV (SDNN, not RMSSD) opportunistically during Breathe sessions and ad-hoc daytime reads, so an Apple HRV series has a completely different noise structure and diurnal composition than an Oura/Whoop nocturnal series.

> Physiological Reports 2025 — https://pmc.ncbi.nlm.nih.gov/articles/PMC12367097/

### Sleep staging is weak across all six major devices; total sleep time is biased +6 to +40 min with ±150 min limits
*[strong]*

Sleep Advances (Oxford UP) 6(2):zpaf021, published 22 March 2025. 62 adults (52M/10F, 46.0 ± 12.6 y), one in-lab PSG night each. TST bias [LoA] in minutes: Fitbit Sense +6.31 [-124.70, +137.32]; Fitbit Charge 5 +11.12 [-70.27, +92.50]; Apple Watch Series 8 +19.60 [-38.35, +77.55]; WHOOP 4.0 +24.46 [-101.09, +150.01]; Garmin Vivosmart 4 +38.44 [-82.63, +159.51]; Withings ScanWatch +39.87 [-92.58, +172.31]. Epoch-by-epoch: Apple Watch S8 kappa 0.53, sens 96.27%, spec 52.15%; Fitbit Sense kappa 0.42; Fitbit Charge 5 0.41; WHOOP 0.37; Withings 0.22; Garmin Vivosmart 4 0.21 (sens 95.92%, spec 29.39%). All devices detect >90% of sleep epochs but specificity is only 29-52% — i.e. they systematically call wake 'sleep', which inflates TST precisely in the post-op patient who wakes repeatedly from pain.

> Sleep Advances 2025, zpaf021 — https://academic.oup.com/sleepadvances/article/6/2/zpaf021/8090472

### Consumer SpO2 error is 2-6% MAE with 11-31% missing measurements — not usable as an infection trigger alone
*[strong]*

PLOS Digital Health 2023, 'Investigating the accuracy of blood oxygen saturation measurements in common consumer smartwatches' (10.1371/journal.pdig.0000296). n=49 (18F/31M; 34.7% Black, 65.3% White; median age 64, median BMI 28.8), reference Masimo MightySat Rx (±2% tolerance). MAE / mean directional error / RMSE: Apple Watch Series 7 2.2% / -0.4% / 2.9%; Garmin Venu 2s 5.8% / +5.5% / 6.7%; Garmin Fenix 6 Pro 3.3% / +1.5% / 3.9%; Withings ScanWatch 3.1% / +1.3% / 3.5%. Unsuccessful-measurement (missingness) rates: Apple 11%, Venu 2s 14%, Fenix 6 Pro 28%, ScanWatch 31%. MAE/RMSE/missingness did not vary significantly by Fitzpatrick skin-tone group, though directional error did show a relationship (p=0.04). Only 3 participants averaged <90% SpO2, so low-saturation behavior is untested — exactly the range that matters for post-op pulmonary complications.

> PLOS Digital Health 2023 — https://journals.plos.org/digitalhealth/article?id=10.1371/journal.pdig.0000296

### Apple Watch SpO2 in the US: removed 18 Jan 2024, restored 14 Aug 2025 with computation moved to the iPhone
*[strong]*

Following the Masimo ITC exclusion order, Apple sold Series 9, Series 10 and Ultra 2 in the US with Blood Oxygen disabled from January 2024. Apple Newsroom, 'An update on Blood Oxygen for Apple Watch in the U.S.' (August 2025): after a US Customs ruling, iOS 18.6.1 + watchOS 11.6.1 (released 14 August 2025) restored the feature via a redesigned architecture in which the watch collects sensor data but the calculation and display happen on the paired iPhone. Practical consequences for our schema: (a) US units purchased Jan 2024-Aug 2025 have a hard SpO2 gap; (b) post-restoration SpO2 requires the paired iPhone and surfaces in the iPhone Health app rather than on-watch, changing sync latency and possibly the HealthKit source device; (c) non-US units and pre-Series 9 US units were never affected. Do not model SpO2 absence as patient non-adherence.

> Apple Newsroom, An update on Blood Oxygen for Apple Watch in the U.S., Aug 2025 — https://www.apple.com/newsroom/2025/08/an-update-on-blood-oxygen-for-apple-watch-in-the-us/ ; AppleInsider 14 Aug 2025

### Temperature: Apple exposes an absolute nightly value in °C, most other vendors expose only a deviation
*[moderate]*

HealthKit's HKQuantityTypeIdentifier.appleSleepingWristTemperature is an absolute wrist temperature in degrees Celsius, sampled overnight on Apple Watch Series 8/Ultra and later (watchOS 9+), requiring continuous skin contact and roughly 5 nights of wear to establish the baseline the Health UI displays as a deviation. Fitbit's Web API splits this into two separate resources — Temperature (Core), which is user-logged manually, and Temperature (Skin), recorded by the device during sleep and expressed as a relative nightly variation from the user's personal baseline, each with 'by Date' and 'by Interval' endpoints. Oura and WHOOP surface nightly deviation/trend rather than a calibrated absolute. Engineering consequence: a canonical Observation store cannot hold one 'skin_temperature' metric — absolute-°C and delta-from-baseline are different quantities with different units and different baseline semantics, and a delta-only vendor gives you no way to reconstruct absolutes.

> Apple Developer, HKQuantityTypeIdentifier.appleSleepingWristTemperature — https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/applesleepingwristtemperature ; Fitbit Web API Temperature — https://dev.fitbit.com/build/reference/web-api/temperature/

### None of the metrics we would use for RTM are FDA-cleared; the cleared set is entirely cardiac/sleep-apnea
*[moderate]*

Cleared as medical devices: Apple ECG app and Irregular Rhythm Notification (De Novo, 2018), Apple AFib History (cleared 2022; in May 2024 became the first digital health technology qualified under FDA's Medical Device Development Tools program as Class II PPG analysis software), Apple Hypertension Notifications (FDA clearance reported by Reuters, 12 September 2025), Samsung Sleep Apnea feature (De Novo, 2024), Fitbit PPG AFib detection (2022). Explicitly general wellness / not cleared: step count, distance, walking speed and all other Mobility metrics, Walking Steadiness, consumer SpO2, HRV, wrist/skin temperature, sleep stages, VO2max/Cardio Fitness, energy expenditure. For Recovery Copilot this means every input to our infection-surveillance composite is wellness-grade: we cannot label an alert a diagnosis, our risk tiers must be framed as triage/escalation prompts with clinician review, and vendor terms for several of these APIs prohibit diagnostic use. It also means the confidence/coverage gate is not optional — it is the regulatory posture.

> Apple ECG/IRN De Novo 2018; IQVIA (May 2024) on AFib History MDDT qualification; Reuters, 12 Sept 2025, FDA clears Apple hypertension notifications; Samsung Sleep Apnea De Novo 2024


## Implications for backend

- Stop treating raw wrist step count as a primary recovery signal in weeks 0-4. Store it, but gate it: add a per-observation `step_confidence` derived from (a) declared assistive device type, (b) estimated walking speed or cadence from the same day, and (c) source device wear location. Concretely, suppress or heavily down-weight step-based tier escalation when assistive_device IN ('walker','rollator') — the documented wrist error there is -36.4% (Apple) and +31.2% magnitude (Fitbit), which is larger than any recovery delta we are trying to detect. A cane needs no correction (-1.9%).
- Model the walker-to-cane-to-unassisted transition explicitly as a covariate in the per-procedure logistic expected-recovery curves. Otherwise the day a TKA patient drops the walker, wrist step count jumps ~35-50% overnight from pure measurement artifact and the curve-fit will register a phantom recovery inflection. Capture assistive_device as a dated, patient-reported timeline (start/stop per device type), and emit a typed reason code (e.g. STEP_ARTIFACT_DEVICE_TRANSITION) whenever a step-count jump coincides within ±2 days of a recorded transition.
- Split the canonical Observation schema for temperature into two distinct metric codes with different units and baseline semantics: `skin_temperature_absolute_c` (Apple appleSleepingWristTemperature, WHOOP absolute) and `skin_temperature_deviation_c` (Fitbit Temperature (Skin) nightly relative, Oura deviation, Apple Health UI display value). Never coerce one into the other. The EWMA/CUSUM baseline machinery must key on (patient, metric_code, provider) because a delta-only vendor has already subtracted its own baseline over its own window — running our baseline on top of theirs double-subtracts and will suppress real fever signal.
- Make HRV baselines provider-scoped and never mix providers within one control chart. Apple emits SDNN sampled opportunistically during the day; Oura emits RMSSD averaged over 5-min windows across the whole sleep period; WHOOP weights toward the last slow-wave episode; Polar uses only the first 4 h after sleep onset; Garmin's 'lowest 30-min average in 24 h' has undisclosed timestamps and was excluded from a 2025 validation outright. Store the sampling window as metadata on the metric capability map and refuse to compute a composite deviation index if the patient switched device families mid-episode. Budget measurement noise of roughly ±11-15 ms LOA on RMSSD when setting CUSUM thresholds.
- Treat SpO2 as optional and region/model/date-conditional, not as a coverage failure. Encode in the capability map: Apple Watch Series 9/10/Ultra 2 sold in the US between 2024-01-18 and 2025-08-14 have no Blood Oxygen; after iOS 18.6.1/watchOS 11.6.1 the value is computed on the paired iPhone, so the HealthKit source device and sync latency differ. The coverage/confidence gate should map absent SpO2 to a distinct reason code (SPO2_UNAVAILABLE_REGULATORY) rather than to non-adherence, and the infection composite should renormalize its weights rather than penalize the patient. Also derate SpO2 weight generally: consumer MAE is 2.2-5.8% with 11-31% failed reads.
- Ingest Apple Mobility metrics as an iPhone-sourced, sparse, prefiltered stream — not a daily guaranteed series. They exist only during flat overground walking, are absent during running/stairs/uphill, are entirely disabled under Wheelchair mode, and require the iPhone coupled near the hip plus a current height in the Health app. Persist per-day estimate counts and enforce a minimum-bouts-per-day threshold before any Mobility metric feeds a tier decision; Apple reports >80% of eligible users get >=5 estimates/day, so a nontrivial tail is under-sampled.
- Set change-detection thresholds from published minimal detectable change, not from statistical significance on our own noisy series. Walking speed MDC: 0.08 / 0.14 / 0.23 m/s (10th/50th/90th percentile); step length MDC 0.04-0.12 m; double support MDC 2.06-4.51 percentage points. Do not alert on a walking-speed change smaller than ~0.14 m/s from a single day. Exclude Double Support Time (ICC 0.53 Apple, 0.42-0.58 independent) and Walking Asymmetry (validated only via a knee brace on n=51 young adults) from any automated tier logic; surface them as clinician-facing context only, flagged as exploratory.
- Down-weight sleep duration in the composite and never ingest vendor sleep stages as clinical fact. Wake-detection specificity is 29-52% across all six major devices, so total sleep time is biased +6 to +40 minutes with limits of agreement up to ±150 minutes — the device will smooth over exactly the pain-driven fragmented awakenings that would be our earliest signal. Prefer sleep-fragmentation proxies from nocturnal HR/HRV (validated to ~1-1.4 bpm) over vendor-reported stage percentages.
- Encode regulatory status in the metric capability map as a first-class field (`regulatory_status`: fda_cleared | general_wellness). Everything we currently use — steps, distance, SpO2, HRV, skin temperature, sleep stages, walking steadiness, VO2max, Mobility metrics — is general wellness. This must propagate to the LLM narrative layer as a hard constraint (no diagnostic phrasing), to the risk-tier copy (escalation prompt for clinician review, not a diagnosis), and to any provider-facing export. Reserve `fda_cleared` for the narrow cardiac/sleep-apnea set (Apple ECG, Irregular Rhythm Notification, AFib History, Hypertension Notifications; Samsung Sleep Apnea; Fitbit PPG AFib).

## Open questions

- No study I could locate measures wrist step-count error in an actual post-arthroplasty cohort walking below 0.8 m/s with a walker. The two best sources are healthy young adults (Fitbit, n=11, mean age 24.9) and community-dwelling adults aged 51-80 without recent surgery (PeerJ, n=42). The -36.4% and 31.2% figures should be treated as lower bounds on error for a true week-1 TKA patient, whose gait is slower and more variable than either cohort. Consider a small internal calibration substudy before hard-coding any correction factor.
- Apple has never published a Walking Steadiness validation white paper comparable to the Mobility Metrics one, and I could not retrieve one (the expected URL 404s). The 0-1 steadiness scores in the THA/TKA study (0.49-0.84) therefore have no published accuracy characterization, no stated MDC, and no documented classification thresholds for the OK / Low / Very Low bands. We are consuming an uncharacterized black box that nonetheless was the only metric to separate THA from TKA at 6 and 12 months.
- Whoop, Samsung Galaxy Watch and Oura were absent or thin in the gait/step literature I found. I have no walker-condition step data for Whoop or Samsung at all, and Oura (finger-worn) is likely to behave very differently from a wrist device when both hands grip a walker frame — plausibly better, since the hand still translates forward with the frame, but this is untested. Worth a targeted search before committing to provider ranking.
- Energy expenditure MAPE by brand and VO2max/Cardio Fitness estimate error remain unquantified here. Fuller et al. (JMIR mHealth 2020, 158 publications, 9 brands) concluded EE is the least accurate of the three core metrics but I could not extract the per-brand numbers. Given that EE and VO2max are both derived from HR plus movement — the movement half of which is exactly what breaks in walker gait — I would assume they are unusable in weeks 0-6 until proven otherwise.
- Respiratory rate validation numbers for consumer wearables (bias, MAPE vs capnography or PSG-derived RR) were not retrievable in this pass, despite RR being one of the six vitals in our composite deviation index. This is a gap worth closing, particularly since RR is typically derived from the same nocturnal PPG stream as HRV and may inherit its sampling-window heterogeneity.
- Vendor terms of service for diagnostic/RTM use were not examined. Several consumer wearable APIs (notably Fitbit and Oura) have historically restricted use of their data for medical diagnosis or treatment decisions. Even where the science supports a signal, the contract may not permit the use — this needs a separate legal/API-terms review per provider before the Terra/Junction connectors go live.
- The Apple Watch Blood Oxygen restoration moved computation to the paired iPhone. It is unclear from the sources retrieved whether the resulting HealthKit sample's source device, sample type, or metadata changed in a way that would break a naive dedupe key or provider-attribution logic in our ingestion path. Worth an empirical check against a post-11.6.1 device before launch.