# Objective functional and range-of-motion measures in orthopedic post-op recovery (TKA, THA, ACL, rotator cuff, lumbar fusion): ROM milestones, performance-test norms/MCIDs, gait parameters, step-count trajectories, and wearable measurability

## Summary

The strongest, most backend-ready evidence is the pair of large mymobility/Apple Watch cohort studies (TKA n=686, THA n=612) giving week-by-week passively-collected gait trajectories: all metrics nadir at post-op week 2 (walking speed drops ~22% to 0.79 m/s, gait asymmetry explodes from ~12.5% to ~52.6% after TKA), then recover on metric-specific timetables — THA roughly twice as fast as TKA (speed recovers week 9 vs week 21). Published TKA step-count norms rise from ~1,439 steps/day at week 1 to ~4,781 at week 6 and ~6,344 at week 20, with a 1-year MCID of ~1,227 steps/day and gait-speed MCID of 0.067 m/s. Hard clinical trigger thresholds exist and are surgeon-credible: knee flexion <90 degrees at 6 weeks post-TKA is the classic manipulation-under-anesthesia indication (4.3-4.6% incidence, best results before 12 weeks); ACL return-to-sport requires >=9 months plus >=90% limb symmetry on quadriceps strength and a 4-hop battery (each month of delay to 9 months cuts reinjury 51%; Delaware-Oslo). Rotator cuff rehab is a phase-clock with explicit PROM degree gates (e.g., 90-degree passive forward elevation to exit weeks 0-3; full PROM/AROM by weeks 11-12; strengthening at 13-16 weeks; large tears shifted ~4-8 weeks later). Classic THA hip precautions (no flexion >90 degrees) do not reduce dislocation (2.2% vs 2.0% in 6,900 patients), so they should be presented as surgeon-preference config, not hard rules. Performance tests (TUG, 6MWT, 30s chair stand, 10MWT) have published norms, fall-risk cutoffs (TUG >13.5 s), and MCIDs (6MWT ~74 m post-TKA) and are feasible as guided in-app tests; goniometric ROM, extension lag, isokinetic strength, and hop batteries remain clinic-entered data. Key caveat: Apple double-support-time disagrees with lab systems (roughly 2x), so wearable gait metrics should be used as within-patient deltas, not compared to lab norms.

## Findings

### TKA knee flexion ROM milestones by post-op week
*[moderate]*

Consensus protocol targets: >=90 deg flexion by end of week 1; >=100 deg flexion AND full (0 deg) extension by weeks 2-3; 110-120 deg by weeks 4-6 (typical attainment 0-125 deg by week 6); passive flexion 130+ deg and 90-deg squat by week 12. Long-term goal band 110-125 deg flexion / 0 deg extension. Functional requirements: ~65-70 deg for gait, ~90-100 deg stairs, ~105 deg rising from chair (implicit in protocol goals).

> Stone Clinic TKA rehab protocol; OneStep 'Range of Motion After Knee Replacement' (2023-2025); patient-pop TKA post-op protocol PDF. https://www.stoneclinic.com/total-knee-replacement-rehab-protocol

### Manipulation-under-anesthesia trigger: flexion <90 deg at 6-8 weeks post-TKA
*[strong]*

Classic MUA indication is <90 deg flexion at 6-8 weeks post-op with no ROM progression. Incidence of MUA 4.3-4.6% (cohorts of 3,244 and 800 knees); stiffness prevalence ~4.5%. MUA performed within 12 weeks of index TKA yields the best flexion gains; some surgeons intervene as early as 2-3 weeks. This is the single most actionable ROM alarm a surveillance system can encode for TKA.

> Efficacy of MUA for Stiffness Following TKA: Systematic Review, J Arthroplasty 2017; Issa et al. / PMC4678244; PMC8875955 (2022). https://pmc.ncbi.nlm.nih.gov/articles/PMC6104526/

### TKA passively-collected gait recovery trajectory (n=686, iPhone+Apple Watch)
*[strong]*

Baseline: speed 1.01+/-0.15 m/s, step length 0.60+/-0.08 m, double support 31.4+/-1.5%, walking asymmetry 12.5+/-17.6%. Nadir at week 2: speed 0.79 m/s (-21.8%), step length 0.55 m (-8.3%), double support 32.8% (+4.5%), asymmetry 52.6+/-33.1% (+321%). Return to baseline: asymmetry week 13 (13.9%), speed week 21 (1.00 m/s), double support week 24 (31.5%); step length never recovered within 24 weeks (0.59 m, p=0.004). Gait quality recovers slower than step counts.

> Christensen et al., 'Stepping beyond Counts in Recovery of Total Knee Arthroplasty', Sensors/PMC 2023. https://pmc.ncbi.nlm.nih.gov/articles/PMC10305196/

### THA passively-collected gait recovery trajectory (n=612) — roughly 2x faster than TKA
*[strong]*

Baseline: speed 1.00+/-0.15 m/s, step length 0.59+/-0.07 m, double support 31.3+/-1.4%, asymmetry 12.4+/-12.4%. Nadir week 2: speed 0.79 m/s, step length 0.53 m, double support 32.8%, asymmetry 42.0+/-32.6%. Recovery to baseline: asymmetry week 7, step length week 8, speed week 9, double support week 10; metrics EXCEED baseline by weeks 10-18 (speed 1.03 m/s at week 13). Procedure-specific recovery clocks are therefore mandatory — a TKA curve applied to THA will under-alarm and vice versa.

> 'Stepping Beyond Counts in Recovery of Total Hip Arthroplasty', PMC 2023. https://pmc.ncbi.nlm.nih.gov/articles/PMC10383890/

### MCID/SCB thresholds for wearable gait metrics after TKA
*[moderate]*

Anchor-based MCID at 1 year post-TKA: gait speed 0.067 m/s; daily step count ~1,227 steps/day. Only ~37% of TKA patients reach the proposed 1.34 m/s 'good walking outcome' benchmark. These are the first published MCIDs specific to passively collected (smartphone/watch) gait metrics in arthroplasty.

> 'Establishing MCID and Substantial Clinical Benefit Thresholds for Objective Gait Metrics After TKA', J Arthroplasty 2026 (S0883-5403(26)00326-8). https://www.arthroplastyjournal.org/article/S0883-5403(26)00326-8/fulltext

### Post-TKA/THA daily step-count recovery curves and outcome thresholds
*[moderate]*

TKA normative weekly-averaged daily steps: ~1,439 (week 1) -> ~4,781 (week 6) -> ~6,344 (week 20); largest gains in first 30 days, plateau after ~week 20. Separate cohort at 12 weeks: THA 3,884 vs TKA 2,311 steps/day. Outcome-linked thresholds (adjacent OA/older-adult literature): >6,000 steps/day protective against functional limitation in knee OA; <=4,149 steps/day associated with functional disability over 2 years; ~7,000 steps/day associated with maintained/improved lower-extremity performance 1 year after hip procedures. Step count correlates only weakly with PROMs (change-change correlations negligible) — objective and patient-reported recovery are complementary axes. Sex effect: men increased steps post-TKA (4,970->6,185) while women decreased (5,532->4,652).

> 'Normative Values for Daily Functional Recovery Patterns Following TKA', J Arthroplasty 2024 (S0883540324005436); 'Stepping Toward Objective Outcomes', J Arthroplasty 2017; Cleveland Clinic ConsultQD wearables TKA. https://www.sciencedirect.com/science/article/abs/pii/S0883540324005436

### ACL reconstruction ROM milestones — extension first
*[moderate]*

Protocol consensus: full passive extension 0 deg (equal to contralateral, no hyperextension loss) is the priority by weeks 1-2; flexion ~90 deg by week 1-2, 120-130 deg by weeks 4-6, full flexion by ~week 6. Persistent extension deficit >5-10 deg beyond weeks 4-6 signals arthrofibrosis/cyclops-lesion risk and warrants escalation. Open-chain knee extension restricted to 90-45 deg arc until ~week 12 in most graft types. Running gate: full pain-free ROM, no effusion, quad LSI >=70% (typically ~12 weeks).

> MOON/ACSM PT protocol supplement (LWW 2024); Okoroha ACLR protocol 2026; DAVID Health ACL protocols 2026. https://cdn-links.lww.com/permalink/mss/d/mss_00_00_2024_09_06_cherelstein_msse-d-24-00074_sdc1.pdf

### ACL return-to-sport gate: >=9 months AND >=90% LSI on quads + 4-hop battery
*[strong]*

Delaware-Oslo cohort (Grindem 2016, BJSM): reinjury rate fell 51% for each month RTS was delayed until 9 months post-op; meeting discharge criteria (quadriceps strength index >=90% by isokinetic dynamometry plus LSI >=90% on all 4 hop tests: single hop for distance, triple hop, crossover hop, 6-m timed hop) reduced reinjury risk 75-84%. Every 1% drop in quad symmetry below 90% raised reinjury risk ~3%. Young athletes returning to level-1 sport <9 months: 39.5% reinjury vs 19.4% after 9 months (up to 7x rate in Beischer 2020 cohort). Caveat: LSI overestimates function because the 'healthy' limb also weakens post-injury — absolute strength (e.g., knee-extension torque >=3.0 Nm/kg proposed) increasingly recommended alongside LSI.

> Grindem et al., BJSM 2016, doi:10.1136/bjsports-2016-096031; Beischer et al., JOSPT 2020 (PubMed 32005095); Wellsandt et al., JOSPT 2017. https://pubmed.ncbi.nlm.nih.gov/32005095/

### Rotator cuff repair (small-medium tears) phase clock with explicit PROM degree gates — MGH 2020
*[strong]*

Phase I (0-3 wk): sling with abduction pillow 30-45 deg, PROM only, ER <20 deg in scapular plane, forward elevation <90 deg, NO AROM/AAROM; exit criteria 90 deg PROM elevation, 20 deg PROM ER, 0 deg PROM IR. Phase II (4-6 wk): PROM caps unchanged, begin AAROM; exit adds pain <4/10. Phase III (7-8 wk): sling discontinued, PROM elevation <120 deg, ER <30 deg, initiate AROM; exit 120 deg PROM elevation, 30 deg ER/IR. Phase IV (9-10 wk): PROM elevation <155 deg, ER/IR 45 deg, ER@90abd 60 deg; exit AROM elevation 120 deg. Phase V (11-12 wk): full PROM and AROM. Phase VI (13-16 wk): rotator cuff strengthening; exit requires ER/IR strength >=85% of uninvolved arm and ER/IR ratio >=60%. Phase VII: return to sport 4-6 months. Large/massive tears: shift phases ~4-8 weeks later (AAROM phase 8-10 to 14-18 wk; take conservative approach for tears >3 cm or >1 tendon).

> Massachusetts General Hospital Sports Medicine, Rehabilitation Protocol for Rotator Cuff Repair — Small to Medium Tears (rev. June 2020), built on ASSET consensus (Thigpen, JSES 2016) and AAOS RC CPG 2019. https://www.massgeneral.org/assets/mgh/pdf/orthopaedics/sports-medicine/physical-therapy/rehabilitation-protocol-for-rotator-cuff-repair.pdf

### THA hip precautions do not reduce dislocation — treat as configurable, not universal
*[strong]*

Systematic review of 7 studies, 6,900 posterior-approach THA patients: dislocation 2.2% WITH precautions vs 2.0% WITHOUT (no significant difference); no PROM differences. Traditional posterior precautions (no hip flexion >90 deg, no internal rotation, no adduction past neutral, prescribed 6-12 weeks) are increasingly replaced by 'pose avoidance' (avoid only the COMBINED flexion>90 + IR + adduction position), considered safe with femoral heads >=28 mm. Unrestricted protocols speed return to function.

> Crompton et al., Acta Orthopaedica 2020, doi:10.1080/17453674.2020.1795598; PMC6778163 pose-avoidance study 2019. https://www.tandfonline.com/doi/full/10.1080/17453674.2020.1795598

### OARSI core performance-test set for hip/knee OA and arthroplasty
*[strong]*

OARSI-recommended battery: minimal core = 30-second chair-stand test, 40-m fast-paced walk test, 9-step stair-climb test (20 cm step height, handrail); recommended additions = Timed Up and Go and 6-minute walk test. This is the surgeon-recognized standard set to name in clinician-facing reports for TKA/THA functional tracking.

> Dobson et al., 'OARSI recommended performance-based tests...', Osteoarthritis and Cartilage 2013 (S1063-4584(13)00790-5) + OARSI test manual. https://www.oarsijournal.com/article/S1063-4584(13)00790-5/fulltext

### Performance-test norms, MCIDs, and risk cutoffs (TUG, 6MWT, 30s chair stand)
*[strong]*

6MWT MCID after TKA: 74.3 m overall (anchor-based; 88.6 m for lowest-baseline quartile); knee-OA anchor/distribution MCIDs 73.6/50.7 m; minimal perceived-improvement threshold 26-55 m at 6 months; typical 6-month post-TKA distance ~375-414 m. TUG: MCID ~1.2 s; fall-risk cutoff >13.5 s (community-dwelling older adults, meta-analysis); test-retest r=0.98 in TKA. 30-second chair stand (Rikli & Jones 1999, n=7,183 ages 60-94): 25th-75th percentile men 60-64: 14-19 stands, women 12-17; declines to men 90-94: 7-12, women 4-11; <8 unassisted stands = functional-limitation flag.

> Jakobsen et al. / PMC8969367 (6MWT MCID after TKA, 2022); Naylor et al. PMC5022203; Barry et al., BMC Geriatrics 2014 (TUG 13.5 s meta-analysis, PMC3924230); Rikli & Jones 1999 via CDC/SRALab. https://pmc.ncbi.nlm.nih.gov/articles/PMC8969367/

### Gait-speed ambulation bands and 10-m walk test reference values
*[strong]*

Community-ambulation cutoffs: <0.4 m/s household ambulator; 0.4-0.8 m/s limited community; >0.8 m/s full community ambulator; <1.0 m/s linked to elevated morbidity/mortality. 10MWT MCID 0.10-0.16 m/s across populations (0.16 m/s acute stroke; 0.06 m/s SCI). Healthy age norms: men 70s ~1.26 m/s, 80s-90s ~0.97; women 70s ~1.13, 80s-90s ~0.94. These bands map directly onto risk-tier logic for wearable-measured gait speed.

> Perry et al. classification via SRALab RehabMeasures '10 Meter Walk Test'; Physiopedia 10MWT; Bohannon age norms. https://www.sralab.org/rehabilitation-measures/10-meter-walk-test

### Balance test norms: single-leg stance and Y-Balance injury thresholds
*[moderate]*

Single-leg stance (eyes open) means: 43 s (ages 18-39), 40.3 s (40-49); meta-analysis 60+ (Bohannon): 27.0 s (60-69), 17.2 s (70-79), 8.5 s (80-99). Y-Balance Test (lower quarter): anterior reach asymmetry >4 cm between limbs = ~2.5x lower-extremity injury risk; composite score = sum of 3 normalized reaches / (3 x limb length) x 100, with <95% (cohort-dependent 89-94%) flagged as elevated risk; youth norms 85-115% of leg length.

> Bohannon, 'Single Limb Stance Times: A Descriptive Meta-Analysis', 2006; Plisky et al. YBT-LQ systematic review/meta-analysis, IJSPT; SRALab Lower Quarter YBT. https://www.sralab.org/rehabilitation-measures/lower-quarter-y-balance-test</citation>

### Extension lag / quadriceps lag definition and cutoffs
*[moderate]*

Quadriceps lag = inability to actively reach the passive extension limit; clinically significant cutoff commonly 15 deg of active extension deficit (based on the ~60% increase in quadriceps force required from -15 deg to 0 deg). Physiologic lag in healthy knees is only 2.5-5.0 deg, so any sustained active-passive gap >5-10 deg post-TKA/ACL indicates quadriceps inhibition/weakness requiring targeted intervention (NMES, biofeedback). Requires paired active+passive goniometry — not wearable-measurable.

> Stillman, 'Physiological quadriceps lag: its nature and clinical significance', Aust J Physiother 2004 (PubMed 15574112); McGinn et al., Ann Transl Med — TKA extension lag short-term outcomes. https://pubmed.ncbi.nlm.nih.gov/15574112/

### Lumbar fusion mobility milestones and restrictions
*[moderate]*

Walking from post-op day 1; practical target ~3,500 steps/day in first 2 weeks, building to 20-30 min continuous walks. No BLT (bending, lifting, twisting) for 6 weeks. Return to light/desk activity 4-6 weeks; normal pain-free gait typically 2-4 months; structured PT (core/pelvic strengthening) weeks 6-12; high-impact clearance contingent on radiographic fusion at ~1 year. Early post-op walking volume predicts substantial 6-month physical-function improvement (prospective cohort). Spine ROM itself is intentionally NOT a rehab target early — walking capacity is the objective functional signal to track.

> Gilmore et al., 'Predictors of substantial improvement... is early post-operative walking important?', BMC Musculoskelet Disord 2019 (PMC6737667); Physiopedia Lumbar Fusion Rehabilitation; PMC12249593 ALIF recovery time-course 2025. https://pmc.ncbi.nlm.nih.gov/articles/PMC6737667/

### Wearable validity: what is trustworthy passively vs what is not
*[moderate]*

iPhone/Apple Health gait speed shows GOOD agreement with APDM Mobility Lab across age groups; smartphone 4-m gait speed correlates r=0.94 with video. Step length and asymmetry are usable for within-patient trends (they drove the n=686/n=612 arthroplasty studies). Apple double-support-time shows POOR-TO-MODERATE agreement and reads ~2x lab values (different calculation) — use only as within-patient relative change, never against lab norms. Apple Watch also provides estimated 6MWT distance and stair ascent/descent speed but lacks published validation detail.

> Werner et al., 'Validity and reliability of the Apple Health app on iPhone for measuring gait parameters', Scientific Reports 2023 (PMC10067003); Apple 'Measuring Walking Quality Through iPhone Mobility Metrics' white paper 2021/2022. https://www.nature.com/articles/s41598-023-32550-3

### Measurability map: passive wearable vs guided in-app test vs clinic-only
*[moderate]*

PASSIVE (consumer wearable/phone): daily steps, gait speed, step length, walking asymmetry %, double support % (trend-only), cadence, stair speed, estimated 6MWT, walking-bout duration. GUIDED IN-APP TEST (phone timer/IMU, patient-administered): TUG, 30-s chair stand, single-leg stance time, 10-m/4-m walk test, 2-min walk; possibly phone-inclinometer shoulder elevation and knee flexion self-measurement (validated apps exist, e.g., 'DrGoniometer'-class, +/-3-5 deg vs goniometer). CLINIC-ONLY: goniometric ROM and extension lag, isokinetic quadriceps strength index, 4-hop battery/LSI, Y-Balance, 40-m fast-paced walk, 9-step stair-climb test, formal 6MWT. Backend should tag each metric with its acquisition channel and hold clinic-only fields as sparse, visit-dated observations.

> Synthesis of: PMC10305196/PMC10383890 (passive arthroplasty gait), Scientific Reports 2023 iPhone gait validation, OARSI manual test requirements, MGH/MOON protocols. https://pmc.ncbi.nlm.nih.gov/articles/PMC10305196/


## Implications for backend

- Replace the single generic logistic 'expected recovery curve' with metric-specific, procedure-specific reference trajectories anchored at the week-2 nadir: for TKA encode expected walking speed 0.79 m/s at wk2 recovering to 1.00 m/s by wk21, asymmetry 52.6%->baseline by wk13, double support normalizing by wk24; for THA encode the faster clock (asymmetry wk7, step length wk8, speed wk9, double support wk10, supra-baseline by wk13). Deviation = patient's weekly mean vs cohort curve +/- published SDs.
- Encode step-count percentile curves for TKA (wk1 ~1,439; wk6 ~4,781; wk20 ~6,344 steps/day) and flag patients tracking below ~50% of the expected week value; store long-term outcome thresholds (<=4,149 steps/day = disability risk; >6,000 protective; ~7,000 post-hip) as reason-coded rules, and suppress 'meaningful change' flags below the published MCIDs (gait speed 0.067 m/s, steps 1,227/day, 6MWT 74.3 m, TUG 1.2 s).
- Add a ROM module fed by clinic-entered or guided-photo/goniometer values with hard typed alarms: TKA flexion <90 deg at week 6 -> MUA-evaluation reason code (cite 4.3-4.6% incidence, best outcome <12 wks); ACL extension deficit >5-10 deg persisting past week 4 -> arthrofibrosis reason code; rotator cuff PROM below phase gate (e.g., <90 deg passive elevation at week 3-4) -> stiffness escalation.
- Implement the ACL return-to-sport gate as a checklist object: months_since_surgery >= 9 AND quad_strength_index >= 0.90 AND all four hop LSIs >= 0.90; render the 51%-per-month-delay and 39.5%-vs-19.4% reinjury statistics in the narrative layer. These inputs are clinic-entered, sparse, visit-dated.
- Map wearable gait speed onto ambulation bands as an additional risk-tier input: <0.4 m/s household, 0.4-0.8 limited community, >0.8 community, <1.0 m/s general morbidity marker — but only after week 6 to avoid flagging the universal early nadir.
- Treat Apple double-support-time as trend-only (within-patient z-scores off the patient's own post-op baseline); never compare to lab/published absolute norms because Apple's value reads ~2x instrumented-walkway values.
- Tag every metric with acquisition_channel = {passive_wearable | guided_in_app_test | clinic_visit} in the schema; build guided in-app implementations for TUG (fall-risk alert >13.5 s), 30-s chair stand (<8 stands alert), single-leg stance, and 10-m walk, since these carry surgeon-recognized cutoffs and need only a phone timer/IMU.
- For rotator cuff, model rehab as a phase-state machine keyed on weeks-since-surgery AND tear size (small-medium vs large shifts phases ~4-8 wks) with the MGH degree gates as expected PROM values; for THA, make hip-precaution messaging a surgeon-configurable flag (evidence: precautions do not change the ~2% dislocation rate) rather than hardcoded advice; for lumbar fusion track walking volume (target ~3,500 steps/day in wks 1-2) as the primary objective signal, not spine ROM.
- Stratify step-count expectations by sex (men tend to gain ~+1,200 steps/day post-TKA, women to lose ~-900) to avoid systematic false alarms in female patients, and keep PROMs as a separate axis from activity metrics since change-change correlations are negligible.

## Open questions

- No published MCID or control-limit for wearable walking-asymmetry % — its baseline SD is enormous (12.5 +/- 17.6%), so EWMA/CUSUM parameters for asymmetry need in-house derivation or wide limits.
- The gait-trajectory cohorts (mymobility, mean age ~61-63, iPhone owners, Zimmer Biomet-sponsored) may not generalize to older, sicker, or Android-using RTM populations — does the week-2 nadir depth and recovery slope hold?
- No published week-by-week wearable step or gait curves exist for ACL reconstruction, rotator cuff repair, ankle, or lumbar fusion — the arthroplasty curves cannot be borrowed directly; interim option is percent-of-preop-baseline milestones with wide bands.
- Guided smartphone goniometry (photo/IMU knee flexion, phone-inclinometer shoulder elevation) has small validation studies (~3-5 deg error) but no large post-op cohort validation — is it accurate enough to drive the <90-deg-at-6-weeks MUA alarm, or must that stay clinic-entered?
- Absolute quadriceps strength thresholds (e.g., knee-extension torque >=3.0 Nm/kg) vs LSI for ACL clearance remain contested — which should the RTS checklist require when both are available?
- Whether the 13.5-s TUG fall cutoff (derived in community-dwelling elderly) is valid in the immediate post-arthroplasty window, where nearly all patients transiently exceed it — needs a time-gated application rule.