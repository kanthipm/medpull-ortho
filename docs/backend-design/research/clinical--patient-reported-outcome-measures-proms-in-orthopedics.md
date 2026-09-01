# Patient-Reported Outcome Measures (PROMs) in orthopedics: instruments, MCID/PASS/SCB thresholds, collection cadence, CMS THA/TKA PRO-PM compliance, and wearable-derived PROM prediction

## Summary

Each orthopedic procedure has a small canonical set of PROMs with published clinical-significance thresholds: KOOS JR/HOOS JR for TKA/THA (CMS SCB thresholds: 20 and 22 points of improvement respectively; PASS approximately 63.7-71 and 73.5-81), IKDC/Lysholm/Tegner/KOOS for ACL (IKDC MCID 13.8, PASS approximately 75), ASES/SANE/Constant for rotator cuff (ASES MCID 11.1, SCB 17.5, PASS 86.7), ODI for lumbar spine (MCID 12.8, PASS ≤18-22), FAAM for foot/ankle (MCID 8 ADL/9 Sports), and PROMIS CATs cross-cutting (MCID approximately 4-7 T-score points). Thresholds vary substantially by derivation method — anchor-based MCIDs are validated as superior to distribution-based ones, which often fall below measurement error — and by diagnosis and timepoint, so a credible engine must store (instrument, procedure, timepoint, method)-specific thresholds, not single global numbers. The CMS THA/TKA PRO-PM is now the hard compliance driver: mandatory for the IQR program covering procedures from July 1, 2024, requiring matched pre-op (0-90 days before) and post-op (300-425 days after) KOOS JR/HOOS JR plus specified risk-variable instruments, with ≥50% completeness of matched pairs, first mandatory submission in fall 2026, FY2028 payment impact, and public reporting of percent-achieving-SCB starting 2027; outpatient/ASC mandatory reporting starts with CY2027 procedures. Real-world electronic-only response rates are poor (29-53%), while multimodal reminder strategies reach 70-95%. Early evidence shows wearable data (steps, HR, sleep) can predict 6-week TJA PROM scores as early as postoperative day 11 and classify PROMIS-domain states with AUC 0.62-0.92, but external validation is nearly absent — good enough for internal early-warning proxies, not for replacing collected PROMs.

## Findings

### TKA/THA short forms: KOOS JR and HOOS JR — structure, scoring, and CMS-anchored thresholds
*[strong]*

KOOS JR: 7 items (stiffness, pain, ADL function), each 0-4; Rasch-converted interval score 0-100 (100 = perfect knee, 0 = total disability). HOOS JR: 6 items, same 0-100 scale/direction. Both nonproprietary and free (developed at Hospital for Special Surgery). Thresholds after primary TJA: KOOS JR — distribution-based MCID 4.0-8.7, anchor-based MCID 14.0-30.7, SCB 20 (the CMS PRO-PM threshold), PASS 63.7-71.0 (63.7 achieved by 85.8% at ~1yr). HOOS JR — distribution-based MCID 3.9-11.0, anchor-based MCID 14.8-38.1, SCB 22 (CMS threshold), PASS 73.5-81.0 (76.7 achieved by 83.1%).

> Katakam et al., Defining the PASS for HOOS JR/KOOS JR after primary TJA, J Arthroplasty 2022, https://pubmed.ncbi.nlm.nih.gov/34958538/ ; systematic review J Arthroplasty 2026, https://www.arthroplastyjournal.org/article/S0883-5403(26)00050-1/fulltext ; HSS instrument page https://www.hss.edu/research/healthcare-research-institute/hoos-koos

### Anchor-based MCIDs are valid for HOOS/KOOS; distribution-based MCIDs fall below measurement error
*[strong]*

In 2,323 THA (mean age 73±6, 57% F) and 2,630 TKA (74±6, 63% F) patients followed pre-op to 2 years, distribution-based MCIDs (6-9 points) never exceeded even small minimal detectable change, while anchor-based MCIDs ranged 7-36 and SCBs 15-36 across all HOOS/KOOS domains and JR versions, all exceeding MDC95. Engineering implication: encode anchor-based thresholds; treat distribution-based values as noise floors only.

> Lyman et al., What Are the Minimal and Substantial Improvements in the HOOS and KOOS and JR Versions After Total Joint Replacement?, Clin Orthop Relat Res 2018, https://pubmed.ncbi.nlm.nih.gov/30179951/

### Oxford Knee/Hip Scores: 12 items, 0-48 (48 best), MCID ~5-7, PASS rises with time from surgery
*[strong]*

OKS after TKA: MCID 5-7 points (7 for primary TKA; ~5 commonly used); PASS 27 (95% CI 26-28) at 3 months, 30 (29-31) at 12 months and 2 years (another cohort: 28 at 6 mo, 32 at 12 mo). OHS after THA: MCID ~4.5-5.0; registry-based PASS (n=597): 34 (CI 31-36) at 3 months, 40 (36-44) at 1 year, 39 (35-42) at 2 years. Licensing: copyright Oxford University Innovation — license required (free for some clinical/unfunded academic use, fees for commercial products). Note PASS thresholds are timepoint-dependent and must be stored per timepoint.

> Registry-based PASS study for OHS, Acta Orthop 2021, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8023959/ ; OKS MCID after TKA, https://www.researchgate.net/publication/258766766

### CMS THA/TKA PRO-PM: mandatory mechanics — instruments, windows, completeness, timeline
*[strong]*

Eligible: Medicare FFS, age ≥65, elective primary THA/TKA (incl. bilateral); excluded: revisions, fractures, malignancy, partial procedures. Required instruments: HOOS JR (THA) / KOOS JR (TKA) plus risk variables: PROMIS-Global OR VR-12 (mental health), Single Item Literacy Screener (SILS-2), and Oswestry back-pain items. Windows: pre-op 0-90 days before procedure; post-op 300-425 days after. Completeness: matched pre+post pairs on ≥50% of eligible patients to satisfy Hospital IQR (failure risks the annual payment update reduction). Timeline: voluntary submissions 2025-2026 (scores confidential; participation rates public); first MANDATORY cohort = procedures July 1, 2024-June 30, 2025 (pre-op collectible from April 2, 2024), post-op follow-through runs to late Aug 2026, submission fall 2026, affecting FY2028 payment determination; public reporting of % achieving SCB (KOOS JR ≥20, HOOS JR ≥22 improvement) begins 2027. Outpatient/ASC version: mandatory for procedures Jan 1-Dec 31, 2027, affecting CY2030 payment determination.

> Medisolv, A Quick Guide to the THA/TKA PRO-PM, https://blog.medisolv.com/articles/tha-tka-pro-pm ; AAOS PRO-PM FAQ, https://www.aaos.org/globalassets/quality-and-practice-resources/patient-reported-outcome-measures/pro-pm-frequently-asked-questions-fact-sheet.pdf ; J Arthroplasty 2025 outpatient/ASC review, https://www.arthroplastyjournal.org/article/S0883-5403(25)01301-4/fulltext

### ACL reconstruction: IKDC, Lysholm, Tegner, KOOS thresholds
*[strong]*

IKDC-SKF (18 items, 0-100, higher better): MCID 13.8; PASS 75.9 (83% sens, 96% spec, ~41-month follow-up, Muller et al.) or 75 (Beletsky, 6mo-2yr cohorts). Lysholm (8 items, 0-100): MCID 9.9; new 2025 PASS thresholds published for post-ACLR patients. Tegner activity (0-10): MCID 0.5. KOOS: MCID ~8/100; PASS by subscale 57.1 (Symptoms) to 92.3-100 (ADL), KOOS QoL PASS ~50. PROMIS CAT MCIDs after ACLR (anchor-based): PF +4.5, Pain Interference -5.4, Depression -4.1; pre-op PROMIS scores predict MCID achievement. Sports-medicine cohorts (e.g., MOON) collect at pre-op, 6 months, 1, 2 years (with 3 and 9 months common clinically for return-to-sport tracking).

> Systematic review of MCID/PASS/SCB after knee ligament reconstruction, Eur J Trauma Emerg Surg 2025, https://pubmed.ncbi.nlm.nih.gov/39843864/ ; Lysholm PASS after ACLR, OJSM 2025, https://pmc.ncbi.nlm.nih.gov/articles/PMC12868573/ ; PROMIS CAT after ACLR, https://pubmed.ncbi.nlm.nih.gov/34977645/

### Rotator cuff repair: ASES, SANE, Constant-Murley, UCLA thresholds
*[strong]*

ASES (0-100, higher better; 50% pain VAS + 50% 10 function items; free): after arthroscopic RCR, MCID 11.1, SCB 17.5, PASS 86.7 (Cvetanovich/Cole 2019, ~1yr); other cohorts report anchor MCID 6.1-13.3, distribution 16.6-26.3. SANE (single item 0-100): MCID 16.9 after RCR. Constant-Murley (0-100; includes clinician-measured ROM and dynamometer strength — not a pure PRO, requires in-person exam): MCID 10.4 points (3-month anchor); alternates 5.5 (ROC) to 9.8. DASH (30 items) / QuickDASH (11 items), 0-100 higher = WORSE (direction inverted vs ASES); free from Institute for Work & Health; Constant/DASH MCB and SCB also published for calcific tendinitis cohorts. Note: reaching MCID/SCB/PASS does not perfectly correlate with patient satisfaction.

> Cvetanovich et al., Establishing clinically significant outcome after arthroscopic rotator cuff repair, JSES 2019, https://pubmed.ncbi.nlm.nih.gov/30685283/ ; Constant MCID, https://pubmed.ncbi.nlm.nih.gov/23850308/ ; UCLA/ASES MCID after RCR, https://pubmed.ncbi.nlm.nih.gov/33746073/

### Lumbar spine surgery: ODI is the anchor instrument; MCID 12.8, PASS ≤18-22, timepoint-dependent
*[strong]*

ODI: 10 items, scored 0-100% (higher = worse disability). MCID 12.8 points (Copay et al. 2008, n=497 one/two-level lumbar fusions; method range 2.9-15.4). Achievement rates: 82.1% reached MCID after single-level fusion; 74.6% in elderly decompression+fusion. PASS: ≤18.09 at 6 months and ≤15.27 at 2 years after single-level fusion for degenerative spondylolisthesis; ≤22 in mixed lumbar degenerative surgery. Pain scales for spine: NRS back/leg pain MCID ~1.2-2.8 points (2.0 commonly operationalized). Cervical analogue (if NDI needed): NDI 10 items 0-50 (often expressed %), MCID 8.5 points/17.3% (Parker et al.), VAS neck 2.6, VAS arm 4.1, SF-12 PCS 8.1 after cervical fusion.

> Copay et al., Spine J 2008, https://pubmed.ncbi.nlm.nih.gov/18201937/ ; PASS for ODI after single-level fusion, Spine J 2021, https://pubmed.ncbi.nlm.nih.gov/33221514/ ; ODI at 3 months in fusion, NASSJ 2024, https://www.nassopenaccess.org/article/S2666-5484(24)00264-6/fulltext

### Foot/ankle: FAAM subscales and PROMIS foot-ankle MCIDs
*[moderate]*

FAAM ADL subscale: 21 items, 0-100 (higher better), MCID 8 points, MDC 5.7, test-retest ICC 0.89. FAAM Sports subscale: 8 items, 0-100, MCID 9 points, MDC 12.3, ICC 0.87 (derived in broad lower-leg/foot/ankle musculoskeletal populations, 4-week rehabilitation anchor — flag: original derivation is 2005, older than preferred). PROMIS and FAAM MCIDs in foot/ankle orthopedics have been jointly established (PMC6698160): PROMIS PF CAT MCIDs in foot/ankle surgery cluster around 4-5 T-score points. FAAM is free to use.

> Martin et al., Evidence of validity for FAAM, Foot Ankle Int 2005, https://pubmed.ncbi.nlm.nih.gov/16309613/ ; PROMIS and FAAM MCIDs in Foot and Ankle Orthopedics, Foot Ankle Orthop 2019, https://pmc.ncbi.nlm.nih.gov/articles/PMC6698160/ ; RehabMeasures, https://www.sralab.org/rehabilitation-measures/foot-and-ankle-ability-measures

### Meniscus surgery: MCID/SCB/PASS at 6-7 months and 1 year after arthroscopic partial meniscectomy
*[moderate]*

At 6-7 months post-APM (n=269): IKDC MCID/SCB/PASS = 10.6/25.3/57.9; KOOS JR = 10.7/13.2/68.3; KOOS Pain = 9.7/22.2/76.4 (per source table); KOOS QoL = 15.6/34.4/46.9. At 1 year: MCID 4.2 (KOOS Pain), 7.2 (ADL), 12.4 (QoL), 25.2 (KOOS JR); PASS 65.5 (IKDC), 84.7 (KOOS Pain), 76.3 (KOOS JR), 53.1 (KOOS QoL). Systematic-review MCID ranges across meniscal surgery: KOOS Symptoms 6.4-10.4, Pain 1.4-12, ADL 3.7-12, Sport 11.8-18.4, QoL 3.1-15.6 — wide variability; only ~50% of patients >40 years achieve PASS at 6 months after APM. Meniscal repair has separate published MCID/PASS (Maheshwer 2021).

> Factors Associated With Clinically Significant PROs After Primary APM, Arthroscopy 2019, https://www.arthroscopyjournal.org/article/S0749-8063(18)31191-5/abstract ; Kovacevic et al., systematic review, OJSM 2026, https://journals.sagepub.com/doi/10.1177/23259671251403143 ; PASS >40yo after APM, https://pmc.ncbi.nlm.nih.gov/articles/PMC9971894/

### PROMIS CATs: T-score metric, low burden, procedure-specific MCIDs of ~4-7 points
*[strong]*

PROMIS domains relevant to orthopedics: Physical Function (PF), Pain Interference (PI), Upper Extremity, Depression, Global-10. CAT administration: typically 4-8 items per domain (max 12), T-score metric mean 50/SD 10 vs US population; free to use (HealthMeasures). MCIDs vary by procedure: distal radius fracture surgery PF 5.2, PI 6.8; ACLR PF +4.5, PI -5.4, Depression -4.1; spine pain populations PF 4.2, PI 3.7. Direction: PF higher = better; PI/Depression higher = worse. PROMIS Global-10 (or VR-12) is an accepted CMS PRO-PM mental-health risk variable.

> Distal radius PROMIS MCID, J Hand Surg 2021, https://www.sciencedirect.com/science/article/abs/pii/S0363502321006006 ; Yedulla et al., PROMIS CAT after ACLR, Arthrosc Sports Med Rehabil 2021, https://pubmed.ncbi.nlm.nih.gov/34977645/

### Generic instruments: EQ-5D-5L, VR-12/SF-12, VAS/NRS pain — scoring and thresholds
*[moderate]*

EQ-5D-5L: 5 dimensions x 5 levels + EQ-VAS; index utility roughly -0.6 to 1.0. MCID in arthroplasty: 0.20 (knee) and 0.17 (hip) utility points (Australian cohort); TKA MID 0.23 at 6 weeks, 0.26 at 6 months. Licensing via EuroQol registration (free non-commercial; fees for commercial). VR-12/SF-12: PCS/MCS norm-based mean 50/SD 10; VR-12 free (used in CMS PRO-PM); SF-12 licensed (QualityMetric). SF-12 PCS MCID after TKA ~4-5 points. VAS/NRS pain 0-10: postoperative MCID ~1.5-2.0 points; spine-specific values 1.2 (back) to 4.1 (VAS arm, cervical). WOMAC: 24 items (5 pain, 2 stiffness, 17 function), Likert 0-96 total (higher = worse), copyright-licensed per study via WOMAC.org (fee-based) — WOMAC subscores are computable from full KOOS/HOOS, which are free, a practical licensing workaround.

> EQ-5D-5L evaluation in knee arthroplasty, Health Qual Life Outcomes 2023, https://pmc.ncbi.nlm.nih.gov/articles/PMC10170024/ ; WOMAC licensing, ePROVIDE/Mapi Trust, https://eprovide.mapi-trust.org/instruments/western-ontario-and-mcmaster-universities-arthritis-index

### Recommended collection cadence: ICHOM standard set plus CMS windows define the schedule
*[moderate]*

ICHOM Hip & Knee OA Standard Set: baseline within a 3-month window pre-surgery, then annual collection at 10-14 months from baseline or previous timepoint. Common clinical/registry practice adds: 2 weeks (early recovery/complication window), 6 weeks, 3 months, 6 months, 1 year, then annually. Sports procedures (ACL, meniscus): pre-op, 3, 6, 9 (return-to-sport), 12, 24 months. Spine: pre-op, 6 weeks, 3, 6, 12, 24 months (3-month ODI shown to be an adequate early proxy in single-level fusion — NASSJ 2024). CMS PRO-PM imposes exactly two mandatory anchors: pre-op 0-90 days before and post-op 300-425 days after surgery; any product schedule must guarantee captures inside both windows.

> ICHOM Hip & Knee Osteoarthritis Reference Guide, https://ichom.org/files/medical-conditions/hip-knee-osteoarthritis/hip-knee-osteoarthritis-reference-guide.pdf ; ICHOM feasibility study, J Patient Rep Outcomes 2018, https://link.springer.com/article/10.1186/s41687-018-0062-5

### Realistic response rates: 29-53% for portal-only electronic collection; 70-95% with multimodal reminders
*[strong]*

EHR-portal-integrated collection: 29-42% response by department, provider-level 13-52%. Modality comparison: phone 71.5% vs paper 57.6% vs electronic 53.2%. Automated electronic reminders with real-time monitoring and staff follow-up achieved 95% completion in longitudinal studies. Dedicated PROM teams using phone/mail reach 70-80%. ISAR (International Society of Arthroplasty Registries) PROMs Working Group benchmark: ≥60% response. Compliance predictors: very young or very old age and non-White race predict lower response; in-clinic tablet capture at pre-op visit is the highest-yield single tactic for the pre-op window.

> EHR-integrated PROM collection, BMC Health Serv Res 2021, https://pubmed.ncbi.nlm.nih.gov/34193125/ ; automated vs combined collection, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6545294/ ; strategies review, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6994453/ ; compliance disparities, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10661514/

### Wearable data can predict 6-week TJA PROM scores by postoperative day 11 (pilot evidence)
*[weak]*

Bloomfield/Ramkumar prospective trial: 22 TJA patients, 3 activity trackers, 35 features collected from 4 weeks pre-op to 6 weeks post-op; ML models accurately predicted 6-week HOOS/KOOS and VR-12 PCS as early as day 11 post-op. Companion study: sampling wearable data more frequently than the standard 24-hour daily aggregate significantly improves 6-week PROM prediction. Caveat: n=22, internal validation only — treat as proof-of-concept for an early-warning PROM proxy, not a validated substitute.

> Bloomfield et al., ML Algorithms Can Use Wearable Sensor Data to Accurately Predict Six-Week PRO Scores Following Joint Replacement, J Arthroplasty 2019, https://pubmed.ncbi.nlm.nih.gov/31439405/ ; optimal sampling frequency, https://pubmed.ncbi.nlm.nih.gov/31445866/

### Systematic review of wearable+ML outcome prediction: AUC 0.62-0.92 for PROMIS-domain classification, almost no external validation
*[moderate]*

18 studies (2017-2024; n=6-2,001, mean 188; monitoring 6h-6mo, mean 54 days; Fitbit most common device). Predictive features: step count, HRV, sleep duration, activity patterns, respiratory rate, gait metrics. Binary classification performance: PROMIS Physical Function AUC 0.75-0.79; Pain Interference 0.62-0.92; Fatigue 0.65-0.89; Sleep Disturbance 0.65-0.88; Anxiety/Depression 0.59-0.92; post-surgical pain accuracy 80-86%; TUG correlation rho=0.67/AUC 0.89; 6MWT accuracy 93%. Random Forest most used (10/18); Hidden Markov Models best exploited longitudinal structure (p<0.05); non-linear beat linear in 7 of 9 comparisons; deep learning showed no clear advantage (63-86%). Only 2/18 externally validated; wearable adherence 59-85%; binary outperformed continuous prediction — meaning score regression (predicting exact KOOS values) is not yet reliable, but above/below-PASS classification is feasible.

> Wearable Technology and ML for Prediction of Performance-Based and Patient-Reported Outcome Measures: A Systematic Review, Sensors 2026;26(4):1218, https://pmc.ncbi.nlm.nih.gov/articles/PMC12943912/

### Threshold variability is diagnosis- and timepoint-specific — a single global MCID per instrument is indefensible
*[strong]*

Diagnosis-specific MCID/PASS for KOOS after TKA and HOOS after THA differ by underlying diagnosis (primary OA vs dysplasia vs osteonecrosis vs revision etiology; J Arthroplasty 2024-2025 series). PASS values shift with follow-up time (OKS PASS 27 at 3mo vs 30 at 2yr; ODI PASS 18.1 at 6mo vs 15.3 at 2yr; meniscectomy KOOS JR MCID 10.7 at 6mo vs 25.2 at 1yr). Achieving MCID/PASS/SCB does not fully track satisfaction (shown for both RCR and shoulder arthroplasty). Systematic reviews across TJA and knee arthroscopy uniformly flag heterogeneous methodology; anchor-based, procedure-matched, timepoint-matched thresholds are the defensible choice for surgeon-facing claims.

> Diagnosis-specific KOOS thresholds after TKA, J Arthroplasty 2024, https://pubmed.ncbi.nlm.nih.gov/38381811/ ; HOOS after THA, https://www.sciencedirect.com/science/article/abs/pii/S0883540324000779 ; TJA meaningfulness systematic review, https://www.arthroplastyjournal.org/article/S0883-5403(26)00050-1/fulltext


## Implications for backend

- Add a proms_thresholds reference table keyed on (instrument, subscale, procedure, timepoint_window, method) storing MCID, PASS, SCB, MDC, score range, and direction (higher_better boolean). Seed with: KOOS JR SCB 20/PASS ~65, HOOS JR SCB 22/PASS ~77, IKDC MCID 13.8/PASS 75, ASES MCID 11.1/SCB 17.5/PASS 86.7, ODI MCID 12.8/PASS <=18-22, FAAM MCID 8 (ADL)/9 (Sports), OKS MCID 5-7/PASS 27-30, OHS MCID ~5/PASS 34-40, PROMIS PF/PI MCID ~4-7 T-points, EQ-5D-5L MID 0.17-0.20. Always prefer anchor-based values; never expose distribution-based MCIDs as clinical claims.
- Compute per-patient clinical-significance flags at each PROM capture: delta-from-baseline vs MCID and SCB, and absolute score vs PASS — these three booleans (plus which threshold set was used) are what orthopedic surgeons recognize as credible, and %-achieving-SCB is exactly what CMS will publicly report.
- Normalize score direction at ingestion (store a normalized 0-100 higher-is-better value alongside the raw score) because the instrument mix is inconsistent: ODI/NDI/DASH/WOMAC higher = worse, KOOS/HOOS/ASES/IKDC/Lysholm/FAAM higher = better, PROMIS direction differs by domain.
- Encode the CMS PRO-PM state machine per THA/TKA episode: eligibility filter (Medicare FFS, >=65, elective primary, exclusion codes), pre-op capture window [surgery_date - 90d, surgery_date], post-op window [surgery_date + 300d, surgery_date + 425d], required bundle (KOOS JR or HOOS JR + PROMIS-Global or VR-12 + SILS-2 + Oswestry back-pain items), matched-pair completeness tracking with a live >=50% dashboard, and deadlines (first mandatory cohort = procedures 7/1/2024-6/30/2025, submission fall 2026, FY2028 payment impact; ASC/HOPD cohort starts 1/1/2027).
- Schedule PROM pushes at pre-op, 2wk, 6wk, 3mo, 6mo, 12mo (then annually 10-14mo spacing per ICHOM); for ACL/meniscus add 9mo (return-to-sport); prioritize in-clinic tablet capture for pre-op and layer channels (push -> SMS/email -> staff phone call) since portal-only yields 29-53% while multimodal reaches 70-95%; target the ISAR >=60% floor and CMS 50% matched-pair floor, and monitor compliance by age/race subgroups.
- For the wearable-PROM bridge: build a binary classifier (above/below PASS, or on-track for MCID) from existing engine features (step count, resting HR, HRV RMSSD, sleep duration, gait/walking speed) rather than regressing exact scores — literature shows binary AUC 0.62-0.92 but unreliable continuous prediction; surface it as an 'estimated functional state' with explicit uncertainty, use collected PROMs as ground truth to personalize over time, and gate it behind the existing coverage-based confidence logic.
- Licensing guardrails for a commercial product: ship KOOS/HOOS/KOOS JR/HOOS JR, PROMIS, ASES, FAAM, DASH/QuickDASH, ODI, Lysholm, SANE, VR-12 (all free); avoid WOMAC (paid per-study license — derive WOMAC subscores from full KOOS/HOOS if needed) and treat Oxford scores and SF-12/EQ-5D-5L as requiring license agreements before inclusion.
- Emit typed reason codes tied to PROM milestones (e.g., PROM_BELOW_PASS_AT_6MO, PROM_MCID_NOT_REACHED, CMS_PREOP_WINDOW_CLOSING, CMS_POSTOP_WINDOW_OPEN, COMPLETENESS_BELOW_50PCT) so the existing rule-based risk tier and the RTM billing layer can both consume PROM state.

## Open questions

- Exact final CMS measure-spec details for the outpatient/ASC PRO-PM (whether completeness threshold, risk variables, and windows are identical to inpatient) — verify against the CY2025/2026 OPPS/ASC final rules before encoding.
- Whether CMS will raise the 50% completeness threshold in later program years (proposals to step it up have been discussed) and how voluntary-period data quality affects public star presentation in 2027.
- Validated crosswalks between PROMIS CATs and legacy instruments (PROMIS PF to KOOS JR/ODI/ASES) — needed if the product wants one low-burden CAT pipeline while still reporting legacy scores surgeons expect.
- PASS/MCID values for younger, active, non-Medicare populations (ACL, meniscus patients under 40) remain sparse and heterogeneous; the meniscectomy 1-yr KOOS JR MCID of 25.2 vs 10.7 at 6-7mo shows instability that needs a policy decision (which timepoint set to pin).
- No externally validated model yet predicts continuous PROM scores from consumer wearables — an internal validation study on this platform's own TKA/THA cohort (wearable features vs collected KOOS JR/HOOS JR at 6wk and 1yr) would itself be publishable and is likely required before surfacing predictions to surgeons.
- Licensing cost quotes for Oxford scores (Oxford University Innovation) and EQ-5D-5L (EuroQol) for a commercial RTM platform — not published openly; requires direct inquiry.