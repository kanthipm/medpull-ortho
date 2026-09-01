# What orthopedic surgeons and care teams actually want from remote monitoring — alert tolerance, workflow reality, staffing, patient adherence decay, algorithm trust, and lessons from deployed platforms (mymobility, Force Therapeutics, Epic Sepsis Model)

## Summary

Surgeons consistently say they will only look at remote-monitoring output that is (a) risk-stratified to the patients who can actually deteriorate, (b) actionable within a visit that gives them under 8 minutes of face time, and (c) accessible without extra clicks — and they abandon anything that behaves like another inbox. The alert-fatigue literature puts hard bounds on design: clinicians override 49-96% of interruptive alerts, CPOE alert PPVs routinely run below 20%, and primary-care physicians already absorb ~77 notifications/day, so a surveillance engine must be engineered around a precision budget, not a sensitivity budget. The Epic Sepsis Model is the canonical failure: AUC 0.63 in external validation (vendor claimed 0.76-0.83), sensitivity 33%, PPV 12%, alerts fired on 18% of ALL hospitalized patients while missing 67% of sepsis — driven by circular training labels and ignoring deployment prevalence; a PJI-surveillance composite at ~1-2% event prevalence faces even harsher PPV math. The best peer-reviewed ortho RPM evidence (Zimmer mymobility RCT, n=401) shows utilization savings (PT need 60.6% vs 94.6%; surgery-related ED/UC 1.3% vs 5.4%) but equivalent — not better — 1-year KOOS and readmissions, and a Mayo comparative study of postsurgical vitals-based RPM showed no readmission/ED benefit at all; nobody has yet demonstrated earlier complication detection from consumer wearables. Patient adherence decays fast and predictably (device compliance ~84% at surgery to ~46-52% by week 6; active tasks far worse than passive streams: 32% thrice-daily exercise compliance vs <1% missing passive sensor data), and in practice data review is done by care navigators/PTAs and therapists under the RTM monthly-interactive-communication requirement, not by surgeons. Credibility with surgeons requires transparent reason codes, external-validation-style performance reporting, and EHR-adjacent one-glance presentation — only 10 of 59 published ortho ML models have any external validation, which is exactly why surgeons default to skepticism.

## Findings

### Surgeons want risk-stratified enrollment and 'actionable' channels; generic vitals RPM showed zero outcome benefit (Mayo mixed-methods, 2022)
*[moderate]*

Comparative study at a US tertiary academic center (Apr-Dec 2021): 147 postsurgical RPM patients vs 145 controls. 30-day readmission 19.7% vs 20.7% (p=0.84); ED visits 6.8% vs 7.6% (p=0.80); no differences in DVT/PE/SSI/UTI/pneumonia. Patient engagement was high (86% daily vitals adherence, 78% daily symptom-question adherence) yet outcomes were null. Interviews with 9 surgeons: enroll 'the patient population at highest risk for readmission' (low-risk cases offer minimal benefit); only collect measurements that can change treatment; requested additions were wound photography, glucose monitoring for diabetics, and step counts — i.e., objective, complication-specific channels rather than generic vitals. ~50% of interviewed patients reported equipment/connectivity problems.

> Mayo Clinic Proceedings: Digital Health / Coffey et al., 'Postsurgical Remote Patient Monitoring Outcomes and Perceptions: A Mixed-Methods Assessment', 2022. https://pmc.ncbi.nlm.nih.gov/articles/PMC9594118/

### Clinicians using an ortho PGHD platform: benefits real, but workload, 'questionable data utility', and non-tailorable software are the killers (JMIR Human Factors 2025)
*[moderate]*

Qualitative study of 9 early users (surgeons + physiotherapists, Milton Keynes University Hospital, June-July 2022) of a digital ortho platform integrating patient-generated health data. Benefits: improved patient education, enhanced communication/assessment, increased patient motivation and adherence. Challenges named: increased clinician workload, questionable data utility, lack of patient centricity, inability to tailor software to clinical context. Explicit recommendations: improve dashboard design, personalize therapy content, and close the loop by using collected data to change clinical care (not just display it).

> JMIR Human Factors, 'Exploring Clinician Experiences With a Digital Platform Supporting Orthopedic Care That Integrates Patient-Generated Health Data', 2025;12:e65216. https://humanfactors.jmir.org/2025/1/e65216/ (PubMed 40882221)

### Why orthopedic surgeons ignore PROM/monitoring data: time, interpretability, 'five clicks deep', and distrust of unadjusted data (2024 systematic review)
*[moderate]*

Systematic review of 8 qualitative/mixed-methods studies (samples 9-30; only 1 rated high quality). Barriers: no time ('I don't have time'); difficulty interpreting scores and explaining discordant subscales; skepticism ('a lot of effort... for not a lot of surgical gain'); systems 'five clicks deep' or 'onerous to access during clinic visit'; distrust over confounding and inadequate risk adjustment. Facilitators surgeons demanded: education on interpretation, EHR/workflow integration with in-visit accessibility, aggregate benchmarking views, and involving surgeons early in system design. Implication: data must be one glance, risk-adjusted, and rendered at the point of the visit.

> Systematic review of barriers/facilitators to orthopaedic surgeon engagement with PROMs data, 2024. https://pmc.ncbi.nlm.nih.gov/articles/PMC11655713/

### Alert-fatigue hard numbers: 49-96% of CDS alerts are overridden; CPOE alert PPVs usually <20% (as low as 5%)
*[strong]*

AHRQ Making Healthcare Safer IV evidence review: providers override 49-96% of drug-interaction and other interruptive alerts; 88.2% of even 'very severe' DDI alerts overridden; ~4 of 5 overrides judged clinically appropriate — i.e., the alerts were wrong, not the clinicians. Systematic review of CPOE decision support quality (JMIR Med Inform 2018): reported alert PPVs 'usually below 20% and as low as 5%'; medication-alert PPVs ranged 8-83%, ~10x higher when informed by patient-level data. A 2026 systematic review of alert-fatigue measurement (22 studies) found only ONE study with an operational definition of alert fatigue and recommends tracking 'sustained decrease in appropriate alert response rate from an established baseline' as the fatigue metric. Design consequence: target PPV >=20-30% per alert type, log response rates as a first-class metric.

> AHRQ Making Healthcare Safer IV (NCBI Bookshelf NBK600580) https://www.ncbi.nlm.nih.gov/books/NBK600580/; Quality of Decision Support in CPOE: Systematic Review, JMIR Med Inform 2018;6(1):e3 https://medinform.jmir.org/2018/1/e3/; Ray-Wilson et al., Alert fatigue measurement in CDS: systematic review, 2026 (MetroHealth PDF)

### Baseline notification load: PCPs already process ~77 EHR notifications/day (~1 hr+); specialists ~29/day — RPM alerts compete with this
*[strong]*

Murphy et al., JAMA Internal Medicine 2016 research letter: primary care physicians received mean 76.9 inbox notifications/day (up to 113.5 at some sites; 20.2% test results), consuming roughly an hour or more of daily processing time; specialists in the same multispecialty practice received mean 29.1 notifications/day (10.4 test-result related). Any ortho RPM stream that adds more than a handful of items per clinician per day joins a queue that already causes missed results and burnout. Physicians report EHR/desk work consumes 49.2% of ambulatory time vs 27.0% direct face time (Sinsky, Annals Int Med 2016 time-motion, 4 specialties incl. orthopedics).

> Murphy DR et al., 'The Burden of Inbox Notifications in Commercial Electronic Health Records', JAMA Intern Med 2016 (Medscape summary https://www.medscape.com/viewarticle/860457); Sinsky C et al., 'Allocation of Physician Time in Ambulatory Practice', Ann Intern Med 2016 https://www.acpjournals.org/doi/10.7326/M16-0961

### Orthopedic clinic time budget: median 7 min 52 s of direct surgeon-patient time per encounter
*[moderate]*

Time-motion observation of 15 orthopedic surgeons across 1,248 encounters over 3 days (subspecialties: foot/ankle, hand, adult reconstruction, peds, spine, sports): median direct patient care 7 min 52 s per patient; median administrative task time 4 min 18 s per patient. Any monitoring summary a surgeon sees must be consumable in seconds within this envelope; a per-patient review artifact that takes >30-60 s to parse will not be used at clinic scale (30-50 patients/day).

> 'Orthopedic Surgeon Time Allocation During the Clinical Encounter', Journal of Orthopaedic Business, 2025. https://jorthobusiness.org/index.php/jorthobusiness/article/view/65

### Who actually reviews RTM data: care navigators (licensed PTAs) and treating therapists, not surgeons; clinician-owned review collapses at volume
*[moderate]*

Published RTM workflow models: 'clinician-owned' (treating PT does all monitoring/documentation) works only at small volume; 'care-coordinator/hybrid' model scales. In a retrospective case-control MSK study, Care Navigators — licensed physical therapist assistants trained in motivational interviewing — reviewed data, handled HEP questions, drove adherence, provided tech support, and pushed summaries to the treating PT between visits. CMS RTM billing structure encodes this: 98975 (setup/education), 98977 (device supply, requires >=16 days of data/30 days), 98980/98981 (treatment management, first 20 min / each additional 20 min per calendar month, requiring at least one interactive communication with the patient) — billable by PTs/OTs as non-E/M practitioners. Backend must produce a monthly per-patient review packet and time log aligned to these 20-minute increments, addressed to a navigator tier first, surgeon only on escalation.

> CMS Transmittal R11118CP (RTM codes) https://www.cms.gov/files/document/r11118cp.pdf; Retrospective case-control study of in-person PT with RTM, 2025 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12447196/; AC Health RTM workflow guide https://ac-health.com/remote-therapeutic-monitoring-workflow-for-clinics/

### Epic Sepsis Model failure — the canonical cautionary case: AUC 0.63, PPV 12%, alerts on 18% of ALL inpatients, 67% of true cases missed
*[strong]*

Wong et al., JAMA Intern Med 2021 external validation at Michigan Medicine: 27,697 patients / 38,455 hospitalizations, sepsis prevalence 6.6% (2,552). At Epic's recommended threshold (score >=6): sensitivity 33%, specificity 83%, PPV 12%, hospitalization-level AUC 0.63 (95% CI 0.62-0.64) vs vendor-claimed 0.76-0.83. Alerts fired in 18% of all hospitalizations (6,971/38,455); number needed to evaluate = 8 per true case; model missed 67% of sepsis (1,709/2,552) and identified only 7% (183) of cases the clinicians had themselves missed (delayed antibiotics) — i.e., near-zero incremental value. Root causes now standard teaching: proprietary/opaque model, training labels contaminated by clinician suspicion (billing-code sepsis, circularity), no external validation before deployment at hundreds of hospitals, and threshold set without regard to deployment prevalence. Direct lesson for a PJI/infection composite at ~1-2% 90-day prevalence: even AUC 0.85 yields single-digit PPV at high-sensitivity operating points — publish the operating point, expected PPV, and NNE, or lose surgeon trust permanently.

> Wong A et al., 'External Validation of a Widely Implemented Proprietary Sepsis Prediction Model in Hospitalized Patients', JAMA Intern Med 2021;181(8):1065-1070. https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/2781307; Habib et al. editorial, 'The Epic Sepsis Model Falls Short', JAMA Intern Med 2021

### Zimmer Biomet mymobility + Apple Watch RCT (n=401 TKA/UKA): big utilization savings, but NO superiority in outcomes and no demonstrated complication detection
*[strong]*

Prospective multicenter RCT (Crawford et al.; 2021 Mark Coventry Award; 1-year data AAHKS 2022; parent study NCT03737149 targeted ~10,000 patients): patients needing >=1 outpatient PT visit: 60.6% (mymobility) vs 94.6% (control), p<0.001; surgery-related ED/urgent-care visits 1.3% vs 5.4%, p=0.03; 1-year KOOS JR 84.1±14.0 vs 83.8±14.6 (p=0.88, equivalent); pre-op to 1-year KOOS change 31.5 vs 32.1 (p=0.51); readmissions 3.8% vs 2.1% (p=0.36, ns); manipulation-under-anesthesia rates and ROM not compromised (337-patient TKA cohort). Companion RCT (J Arthroplasty 2024, PMID 38211730) showed the app significantly improved PROM completion rates vs paper. What the program has NOT demonstrated: better PROMs, fewer readmissions, earlier complication detection from Apple Watch passive data — the 778-patient passive-data analysis (AAOS 2021) showed only 'associations' between passive metrics and patient-reported pain/function. The commercial win is substitution economics (self-directed rehab replacing PT visits), not surveillance accuracy.

> Zimmer Biomet AAHKS 2022 one-year data release https://www.prnewswire.com/news-releases/zimmer-biomet-announces-one-year-data-from-mymobility-clinical-study-at-2022-aahks-annual-meeting-301669492.html; Crawford et al., J Arthroplasty 2021 (S0883-5403(21)00647-1); PROM-completion RCT, J Arthroplasty 2024, PMID 38211730; NCT03737149

### Force Therapeutics: vendor-reported 26.3% drop in 90-day TJA readmissions in a pre/post single-hospital analysis — weak design, but shows what buyers accept
*[weak]*

Community Hospital of the Monterey Peninsula 1-year retrospective pre/post analysis (announced 2022): all-TJA readmissions fell >26% vs prior year after implementing the Force digital care platform (wound-care education, in-app photo/message triage to care team, custom outcome forms for pain/comfort/mobility); vendor claims average $2,100 savings per MSK episode via reduced unnecessary outpatient services. No randomization, no concurrent control, vendor-published — the evidentiary bar in this market is low, which is both an opportunity (credible analytics differentiate) and a warning (surgeons discount vendor claims). Independent RCT evidence for comparable digital-rehab platforms shows mostly non-inferiority, not superiority.

> Force Therapeutics press release, 'Force Therapeutics Reduces 90-Day Readmissions for Total Joint Arthroplasty Patients', 2022. https://www.forcetherapeutics.com/press-releases/force-therapeutics-reduces-90-day-readmissions-for-total-joint-arthroplasty-patients/

### Wearable compliance decays to ~50% by postop week 6 in shoulder surgery; plan for it, don't fight it
*[moderate]*

Validated sleep-tracking wearable after shoulder surgery (PMC10450855, 2023): device compliance fell from 84% at surgery to 46% at 6 weeks in rotator cuff repair patients, and 81% to 52% in total shoulder arthroplasty — roughly a 5-6 percentage-point loss per week. A 12-week knee RPM study found a critical asymmetry: passive sensor streams had <1% missing daily recordings with no systematic dropout, while weekly PROMs averaged 16.2% missing and prescribed-exercise compliance was 32.3% (thrice-daily regimen) vs 52.4% (once-daily) — halving the demanded frequency raised compliance ~20 points. Backend consequence: the coverage-based confidence gate should encode an expected wear-decay curve (not treat week-5 sparsity as anomalous), weight passive channels over active tasks, and any patient-facing task cadence above 1x/day will fail for most patients.

> 'Validated Wearable Device Shows Acute Postoperative Changes in Sleep Patterns... and Progressive Decreases in Device Compliance After Shoulder Surgery', Arthrosc Sports Med Rehabil 2023 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10450855/; knee RPM 12-week wearable study (JBJS Open Access / PMC8347411)

### Large joint-specific wearable cohort (TracPatch, n=435): passive steps captured for all, but only 43% yielded usable ROM data at 6 weeks; complications detected were rare events
*[moderate]*

Prospective cohort, TracPatch Duo (two 9-DOF IMUs, thigh+shin) after knee arthroplasty: 435 enrolled; total daily steps captured for all 435 (3,976±3,532 preop to 4,997±3,637 at 6 weeks, significant improvement), but flexion/extension ROM data complete to 6 weeks in only 186/435 (42.8%) — active/derived metrics lose more than half the cohort. Clinical events over 6 weeks: 3 deep/prosthetic infections requiring surgery (0.7%) and 4 MUAs (0.9%) — confirming the very low event prevalence any infection-surveillance composite must operate against. Study reported no staff review-time data and no alert-volume data — typical of the literature's silence on operational burden.

> 'Remote Monitoring using Wearable Technology after Knee Arthroplasty Using a Joint-Specific Wearable Device: A Prospective Cohort Study of 435 patients', Journal of Orthopaedic Experience & Innovation, 2023. https://journaloei.scholasticahq.com/article/72644

### Digital divide in the arthroplasty-age population: ~61-65% smartphone ownership at 65+, with a 3x income gradient (81% vs 27%)
*[moderate]*

Pew Research: 61% of US adults 65+ own smartphones (~65% by 2021, Statista); ownership 81% among 65+ households earning >=$75k vs 27% below $30k — device-dependent programs structurally exclude low-income seniors. Real-world geriatric telemedicine onboarding is brutal: in one program, after a mean 4.78 hours of dedicated training per patient across 309 geriatric complex patients, only 18.8% subsequently connected to a provider virtually. mymobility-style iPhone+Apple Watch requirements bias enrollment young/affluent/White (Mayo RPM cohort: 93.3% White, mean age 56.3 in a specialty whose TJA median age is ~66). Backend needs an explicitly supported low-tech tier (phone-call/SMS-entered data) and should track enrollment-eligibility funnel metrics as an equity signal.

> Pew Research via Retirement Living senior cell phone statistics 2026 https://www.retirementliving.com/cell-phones-for-seniors/cell-phones-for-seniors-statistics; Statista smartphone ownership by age https://www.statista.com/statistics/489255/percentage-of-us-smartphone-owners-by-age-group/; geriatric telehealth training cohort (PMC7740507)

### Surgeons say they'd trust AI risk models — but only 10 of 59 published ortho ML models have ANY external validation, and they know it
*[moderate]*

Mass General Brigham spine-surgeon survey (Seminars in Spine Surgery): majority 'likely or very likely' to trust AI-driven risk-stratification models, yet none are in routine care; hesitancy driven by black-box opacity, fear of degradation in new environments, and poor workflow fit. Systematic review (2021, PMC8436968): of 59 ML prediction models for orthopedic surgical outcomes, only 10 had identifiable external validation studies, and reporting quality of those validations was poor. Ortho-trauma ML systematic review (Bone & Joint Open 2024, 45 studies): pervasive overfitting and single-center bias. The credibility recipe the literature converges on: transparent features with clinical rationale (reason codes), calibration reporting (not just AUC), external/temporal validation, and per-site performance monitoring after deployment.

> Availability and reporting quality of external validations of ML prediction models with orthopedic surgical outcomes: systematic review, 2021 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8436968/; Mass General Advances in Motion summary https://advances.massgeneral.org/ortho/journal.aspx?id=2063; Bone & Joint Open ortho-trauma ML review https://boneandjoint.org.uk/Article/10.1302/2633-1462.51.BJO-2023-0095.R1

### Patient-side value proposition is 'peace of mind', and it is fragile to tech friction
*[moderate]*

Across studies: 83.6% of TJA patients willing to wear a monitoring device and ~90% report peace of mind from continuous tracking (PubMed 36465696); Mayo qualitative interviews: dominant patient theme was reassurance that 'the data collected were being reviewed' — meaning patients assume a human is watching, which creates a liability/expectation gap if alerts are ignored; ~half of patients reported equipment/connectivity failures ('when you go to send it, a lot of times it won't go'). Satisfaction 4.7/5 but survey response only 35%. Design consequence: the platform must be able to demonstrate (and log) that transmitted data was reviewed — this is simultaneously the RTM billing evidence trail and the patient trust contract.

> 'Understanding Patient Perspectives Regarding Remote Monitoring Devices Following Total Joint Replacement', 2022, PubMed 36465696 https://pubmed.ncbi.nlm.nih.gov/36465696/; Mayo mixed-methods assessment https://pmc.ncbi.nlm.nih.gov/articles/PMC9594118/

### Physiologic-alarm precedent: the overwhelming majority of continuous-monitoring alarms are non-actionable — continuous vitals streams must be heavily debounced
*[moderate]*

Long-standing hospital alarm literature (Sendelbach & Funk 2013, widely cited in the 2013-2014 Joint Commission National Patient Safety Goal on alarm management) found 72-99% of physiologic monitor alarms are false or non-actionable, which produced the well-documented desensitization that killed clinician response. This is the closest analog to streaming consumer-wearable vitals: raw EWMA/CUSUM crossings on noisy daily HR/HRV/temp series will replicate hospital telemetry alarm behavior unless gated by persistence rules (e.g., N consecutive days), multi-signal concordance, and per-patient suppression after acknowledgment. Flag: pre-2020 literature, but the mechanism is not contested and is embedded in Joint Commission policy.

> Sendelbach S, Funk M. 'Alarm Fatigue: A Patient Safety Concern', AACN Adv Crit Care 2013;24(4):378-386 (basis of Joint Commission NPSG.06.01.01); corroborated by AHRQ Making Healthcare Safer IV https://www.ncbi.nlm.nih.gov/books/NBK600580/


## Implications for backend

- Adopt an explicit precision budget per alert type: compute and persist rolling PPV, number-needed-to-alert, and acknowledged-vs-dismissed response rate for every reason code; target PPV >=20-30% and treat a sustained drop in response rate (the 2026 systematic review's recommended fatigue metric) as an SLO violation that auto-tightens thresholds. At ~1-2% PJI prevalence, publish the operating point and expected NNE next to every infection-surveillance flag (anti-Epic-Sepsis-Model design).
- Debounce the EWMA/CUSUM layer against the 72-99% non-actionable alarm precedent: require persistence (>=2-3 consecutive days out-of-control) and multi-signal concordance (e.g., resting-HR + skin-temp + functional decline together) before emitting HIGH; add per-patient alert suppression/cool-down after clinician acknowledgment; deliver a once-daily digest queue, never interruptive per-event pings — specialists already field ~29 notifications/day and PCPs ~77.
- Build the review workflow for a navigator/PTA tier, not the surgeon: a triage queue sorted by tier with a per-patient monthly packet, a review-time ledger in 20-minute increments mapped to 98980/98981, an interactive-communication log (required monthly for 98980), and a >=16-days-of-data/30-day flag for 98977 eligibility. Surgeon-facing output should be a single glance: tier + top-3 typed reason codes with raw values, consumable inside a 7-minute-52-second encounter, never 'five clicks deep'.
- Encode expected adherence decay into the coverage/confidence gate: expect device wear to fall from ~84% to ~46-52% by week 6 (~5-6 pts/week); parameterize a procedure-agnostic wear-decay prior so week-5 sparsity lowers confidence gracefully instead of triggering MISSING_DATA churn; weight passive streams (steps, HR — <1% missing in studies) above active tasks (PROMs ~16% missing, 3x/day exercise tasks ~32% compliance); cap any patient-facing task cadence at 1x/day.
- Surface the evidence surgeons demand: per-metric calibration and external/temporal-validation stats in the clinician UI, transparent formulas for the composite deviation index (surgeons distrust black boxes; only 10/59 ortho ML models are externally validated), risk-adjusted expected-recovery curves with visible procedure/patient covariates, and aggregate per-surgeon benchmarking views (a documented PROM-engagement facilitator).
- Add risk-stratified enrollment and channel selection: a pre-op readmission/complication risk score gating who gets full RPM (surgeons explicitly say low-risk patients yield nothing), plus the complication-specific channels surgeons asked for — wound photo capture, diabetic glucose flagging, step counts — rather than more generic vitals.
- Log 'data was reviewed' events as a first-class audit record: it is simultaneously the RTM billing evidence trail, the medico-legal defense (patients assume a human watches), and a trust signal to display back to patients.
- Support a low-tech tier (SMS/IVR-entered symptoms, no wearable) and instrument the enrollment funnel by age/income proxy: at 65+, smartphone ownership is ~61-65% with an 81%-vs-27% income gradient, so an iPhone+Watch-only design structurally excludes a large share of the median-age-66 arthroplasty population and skews the analytics training population.

## Open questions

- No published tolerable-alert-volume threshold exists for RTM/RPM specifically (the 22-study alert-fatigue review found only one operational definition of alert fatigue); the per-navigator daily alert budget will have to be set empirically and monitored via response-rate decay.
- Published staffing ratios (patients per navigator/nurse FTE for ortho RPM) were not found — vendor workflow guides describe roles but not quantitative ratios; worth targeted follow-up in AAHKS/AAOS practice-management literature.
- Week-by-week wear-time decay curves specific to TKA/THA consumer wearables (e.g., Ghomrawi's Fitbit work) were not retrieved before the search budget was exhausted; the shoulder-surgery decay curve (84%->46-52% by week 6) is the best quantified proxy captured.
- The Peterson Health Technology Institute's independent evaluation of virtual MSK solutions (Hinge Health, Sword) — reportedly skeptical on clinical-outcome claims — was not verified and would strengthen the 'what platforms failed to demonstrate' case.
- Whether any composite wearable-vitals deviation index has ever been prospectively validated for post-arthroplasty infection detection (sensitivity/specificity/lead time) is unresolved — nothing found suggests one exists, meaning the platform's PJI-surveillance claims need prospective-validation framing, not detection claims.
- The mymobility parent study (NCT03737149, target ~10,000 patients) full peer-reviewed multi-site publication status as of 2026 was not confirmed; the strongest published evidence remains the n=401 and n=337 RCT cohorts.