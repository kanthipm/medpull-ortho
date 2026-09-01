# Value-based care economics for orthopedic episodes: CMS TEAM/CJR/BPCI-A, episode cost structure, quality measures, and 2026 RTM reimbursement — the buying math for an RTM platform

## Summary

The dominant commercial driver in 2026 is CMS's mandatory Transforming Episode Accountability Model (TEAM), which started January 1, 2026 and puts ~700-741 hospitals at two-sided risk for 30-day surgical episodes including lower-extremity joint replacement (LEJR), hip/femur fracture (SHFFT), and spinal fusion, with a 2% built-in CMS discount on LEJR target prices and reconciliation adjusted up to +10%/-15% by a Composite Quality Score that includes the THA/TKA PRO-PM (HOOS Jr./KOOS Jr. with substantial-clinical-benefit thresholds of 22/20 points). BPCI-Advanced ended December 31, 2025 and CJR ended earlier, so TEAM is now the only mandatory game, layered on top of Hospital IQR penalties for failing to collect PROs on >=50% of eligible arthroplasty patients (FY2028 annual payment update at risk). The episode economics that a monitoring platform can move are concentrated in a few line items: post-acute care (~25-40% of a $15,600-$25,000 90-day LEJR episode), SNF stays (>$20,000 vs near-zero incremental cost for home recovery), 90-day readmissions (5.6-12.7% incidence; $9,000-$63,000 per event), periprosthetic joint infection (1-2% incidence; $38,865-$79,223 direct cost for two-stage treatment; $1.85B national burden by 2030), and MUA/stiffness (~4% of TKAs; revision-for-stiffness ~$65,771). On the revenue side, the CY2026 Physician Fee Schedule finalized new short-duration RTM codes (98979 ~$26 for 10-19 min management; 98984/98985 ~$51-52 for 2-15 days of device data) alongside existing codes (98975 ~$22, 98977 ~$40, 98980 ~$54, 98981 ~$41), so a 3-month post-op RTM program bills roughly $400-430 per Medicare patient even before any shared-savings upside. The purchase justification is therefore three-legged: direct RTM billing revenue, TEAM reconciliation dollars from avoided PAC/readmissions/complications, and PRO-PM compliance that protects both the IQR payment update and the TEAM quality multiplier.

## Findings

### TEAM model: mandatory, live now (Jan 1 2026 - Dec 31 2030), 5 surgical episodes, 30-day window
*[strong]*

TEAM began January 1, 2026 and runs five performance years through December 31, 2030. Participation is mandatory for ~700-741 selected acute care hospitals (participant counts of 700, 721, and 741 appear across sources as CMS updated the list) in 188 Core-Based Statistical Areas stratified by historical episode spending, hospital count, safety-net status, and prior bundled-payment experience. Five episode types: lower extremity joint replacement (LEJR, incl. THA/TKA — MS-DRG 469/470 and outpatient HCPCS equivalents), surgical hip/femur fracture treatment (SHFFT), spinal fusion, CABG, and major bowel procedures. Episode = anchor hospitalization/procedure (facility + professional) plus most Medicare Parts A/B costs for 30 days post-discharge, including SNF. Retrospective reconciliation against a pre-set target price, adjusted by quality.

> CMS, "TEAM (Transforming Episode Accountability Model)" (2024-2026), https://www.cms.gov/priorities/innovation/innovation-models/team-model; IMO Health, "The 2026 CMS TEAM model explained" (2025), https://www.imohealth.com/resources/the-2026-cms-team-model-explained/

### TEAM target price methodology: 3-year rolling regional baseline, 2% discount on LEJR, HCC v28 risk adjustment
*[strong]*

Target prices are set per MS-DRG/HCPCS episode type per region (U.S. Census Division) from a rolling 3-year baseline (PY1 2026 uses CY2022-2024 claims), trended forward via log-linear regression on 5 years of standardized/winsorized spending; the prospective trend factor is the simple average of regional and national 2-year factors, with the retrospective (final) trend factor capped at +/-3%. CMS keeps a built-in discount of 2.0% for LEJR, SHFFT, and FUSION episodes (1.5% for CABG/BOWEL) — hospitals must beat regional average spending minus 2% to earn any reconciliation payment. Risk adjustment: HCC Version 28 flags from a 180-day pre-episode lookback binned 0/1/2/3/4+, age bands (<65, 65-74, 75-84, 85+), prior post-acute-care use, disability status (LEJR only), LEJR procedure indicators (ankle, partial hip, THA, partial knee, TKA), social risk (Community Deprivation Index, Part D LIS, dual eligibility), safety-net status (>75th percentile dual/LIS), and bed-size categories (0-250, 251-500, 501-850, 851+). Normalization is budget-neutral in aggregate; final normalization capped within +/-5% of prospective. Milliman's worked LEJR (DRG 469) example: baseline-year-1 average episode $20,000 trending to $25,000 in baseline year 3 (adjustment factor 1.25).

> Milliman, "Demystifying the TEAM target price: A practical walkthrough" (2025), https://www.milliman.com/en/insight/demystifying-cms-team-target-price-practical-walkthrough

### TEAM risk tracks and Composite Quality Score: quality swings reconciliation by +10%/-15%
*[strong]*

Track 1 (PY1, upside-only, no downside); Track 2 (PYs 2-5 for safety-net/rural/limited hospitals, stop-gain/stop-loss +/-10%); Track 3 (PYs 1-5, all participants, stop-gain/stop-loss +/-20% of reconciliation target amount). The Composite Quality Score (CQS) scales reconciliation: it can increase a positive reconciliation amount by up to 10% or reduce a repayment (negative reconciliation) by up to 15% depending on track. Three CQS measures: (1) Hybrid Hospital-Wide All-Cause Readmission (claims+EHR), (2) CMS Patient Safety and Adverse Events Composite (PSI-90), (3) Hospital-Level THA/TKA PRO-PM (CMIT #1618) — the PRO-PM applies to all inpatient LEJR episodes PY1-PY5, so an RTM platform that captures HOOS Jr./KOOS Jr. directly moves the payment multiplier. Exact TEAM-specific measure weights are codified at 42 CFR 512.547 (finalized in FY25 IPPS rule).

> CMS TEAM quality scoring fact sheet (team-qualityscoring-fs.pdf, 2024); Code Technology, "THA/TKA PRO-PM and the TEAM Composite Quality Score" (2025), https://www.codetechnology.com/blog/tha-tka-pro-pm-team-quality-score/; McDermott+, "CMMI Finalizes TEAM" (2024), https://www.mcdermottplus.com/blog/regs-eggs/cmmi-finalizes-team-comparison-of-proposed-and-final-policies/

### THA/TKA PRO-PM mechanics: HOOS Jr. >=22 / KOOS Jr. >=20 point gain, 50% matching, FY2028 IQR penalty
*[strong]*

The PRO-PM = risk-standardized proportion of elective primary THA/TKA patients achieving substantial clinical benefit (SCB): >=22-point improvement on HOOS Jr. (hip) or >=20-point on KOOS Jr. (knee), pre-op to post-op. Collection windows: pre-op survey within 90 days BEFORE surgery; post-op between 300 and 425 days AFTER surgery; both the joint instrument and required risk-adjustment/health items must be completed at both timepoints to count as a matched pair. Hospitals must submit matched data on >=50% of eligible patients; mandatory Hospital IQR reporting began with procedures July 1, 2024 - June 30, 2025 and feeds the FY2028 annual payment update (failure risks the IQR reduction — one-quarter of the market-basket update). CMS requires >=25 matched pairs to compute a reportable risk-standardized improvement rate. An outpatient/ASC version of the PRO-PM was finalized in the OPPS/ASC rules as arthroplasty migrates out of the hospital.

> Medisolv, "A Quick Guide to the THA/TKA PRO-PM Measure" (2024-2025), https://blog.medisolv.com/articles/tha-tka-pro-pm; AAOS IQR resources, https://www.aaos.org/registries/quality-collaborations/iqr-resources/; Qualityreportingcenter FY2028 IQR Program Guide (2026)

### CJR results and BPCI-Advanced sunset: bundles reliably saved ~$1,000/episode, mostly from PAC
*[strong]*

CJR (2016-2024, mandatory LEJR bundles, 90-day episode) is the direct ancestor of TEAM. NEJM 2-year evaluation: average episode payments fell 3.7% ($146M total), predominantly via reduced institutional post-acute care use. CJR PY6 evaluation: net reduction ~$1,012 per episode (3.5% of baseline). CMS reported $112.7M Medicare savings across 323 hospitals and 98,000+ episodes in 2021-2023 (PY7) with quality maintained. BPCI-Advanced (voluntary, 90-day clinical-episode bundles including MJRLE) ended December 31, 2025 — practices that were in BPCI-A now have TEAM (30-day, hospital-anchored) as the only CMS bundle. A CMS "CJR-X" (CJR Expanded) model page appeared on cms.gov in 2026 — details unverified in this research pass (fetch blocked).

> Barnett et al., "Two-Year Evaluation of Mandatory Bundled Payments for Joint Replacement," NEJM 2019, https://www.nejm.org/doi/full/10.1056/NEJMsa1809010; CMS CJR PY6/PY7 evaluation reports, https://www.cms.gov/priorities/innovation/data-and-reports/2025/cjr-py7-ar-exec-sum; CMS Innovation Insight on CJR savings

### 90-day LEJR episode cost structure: ~$15,600-$25,000, with post-acute care ~25-40% of spend
*[moderate]*

Median Medicare 90-day episode expenditure for TKA: $15,587 (2018 dollars); median PAC spending within the episode $3,817-$4,195 (~24-27%); older CJR-era averages ran $20,000-$25,000+ per LEJR episode (Milliman's TEAM example uses $20,000-$25,000 for DRG 469), with CMS/CJR literature historically attributing up to ~40% of episode variation to PAC. Within the 90 days post-TKA, Medicare spends >$3,000/patient, of which >$2,500 is outpatient services and 83% of that is physical therapy — the exact spend RTM-guided home exercise can substitute. Bundled-payment savings in every major evaluation came overwhelmingly from cutting institutional PAC (SNF/IRF), not from the index admission.

> "Ninety-day and one-year healthcare utilization and costs after knee arthroplasty," PMC6750955 (2019), https://pmc.ncbi.nlm.nih.gov/articles/PMC6750955/; NEJM CJR evaluation 2019; Milliman TEAM walkthrough 2025

### Readmission economics: 5.6-12.7% 90-day incidence; $9,000-$63,000 per readmission event
*[moderate]*

Historical Medicare 90-day readmission rates: 12.7% THA, 9.6% TKA; a contemporary (2024, HSS) single-system analysis found 5.6% for both. Cost per readmission varies by methodology: $9,335 average 90-day TKA readmission (bundled-payment cost analysis); readmissions for surgical complications cost $51,769 (THA) and $45,223 (TKA) vs medical-complication readmissions (Journal of Arthroplasty 2019); a 2024 analysis reported average readmission costs of $63,452 (THA) and $61,050 (TKA) (likely charge-based — treat as upper bound). National annual burden: Medicare pays ~$319M/yr for 90-day THA readmissions (67% of total) and ~$417M/yr for TKA (66%). Under TEAM, only the first 30 days land inside the episode, but the Hybrid Hospital-Wide Readmission measure in the CQS and the HRRP (which includes elective THA/TKA, penalty up to 3% of all Medicare inpatient payments) keep 30-day readmissions penalized at hospital level.

> Bido et al., "Early Readmission and Revision After TJA," HSS Journal 2024, https://pmc.ncbi.nlm.nih.gov/articles/PMC11393636/; Kurtz et al., PMC5670047 (2017); "Patterns and Costs of 90-Day Readmission," J Arthroplasty 2019, https://pubmed.ncbi.nlm.nih.gov/31279598/

### PJI is the dominant single-complication cost: $38,865-$79,223 per two-stage course; $1.85B national by 2030
*[strong]*

PJI affects 1-2% of primary joint replacements. Median 2-year direct costs of two-stage exchange for hip PJI: $38,865 when reimplantation succeeds without further surgery vs $79,223 when additional revision is required (Arthroplasty Today 2022); mean total cost of 2-stage TKA revision ~$37,980; operative PJI treatment costs are ~2x aseptic revision (a septic revision runs ~$60,000 more than aseptic loosening revision in some analyses). Combined annual US hospital costs for hip+knee PJI are projected to reach $1.85 billion by 2030 (Premkumar et al., J Arthroplasty 2021). For a bundled episode, a single PJI readmission inside the 30-day TEAM window can single-handedly wipe out the reconciliation surplus of 20-40 clean episodes — this is the core actuarial argument for infection-surveillance monitoring (the platform's composite deviation index).

> "Direct Costs Vary by Outcome in Two-Stage Revision for Hip PJI," Arthroplasty Today 2022, https://pmc.ncbi.nlm.nih.gov/articles/PMC9713268/; Premkumar et al., "Projected Economic Burden of PJI of the Hip and Knee in the US," J Arthroplasty 2021, https://www.sciencedirect.com/science/article/abs/pii/S0883540320312444

### Stiffness/MUA economics: ~4% of TKAs get MUA; revision for stiffness costs $65,771; $8.75B national arthrofibrosis burden
*[moderate]*

Post-TKA stiffness prevalence 1.3-6.1%; manipulation under anesthesia performed in ~4% of TKA patients. Patients with stiff TKA incur significantly higher costs for all treatments: dual-component revision $65,771 (stiff) vs $48,287 (non-stiff) ("The Cost of Stiffness After TKA," J Arthroplasty 2023). Arthrofibrosis burden estimated at $8.75B annually in the US. 17.2% of MUA patients require reoperation. Because MUA typically happens weeks 6-12, RTM-tracked ROM/steps trajectories that flag stalled flexion before week 6 map directly to an avoidable-cost line a surgeon recognizes.

> "The Cost of Stiffness After Total Knee Arthroplasty," J Arthroplasty 2023, https://pubmed.ncbi.nlm.nih.gov/36947505/; "Failure Incidence and Predictors Following MUA," J Arthroplasty 2026, https://www.sciencedirect.com/science/article/abs/pii/S0883540326002482

### SNF vs home recovery: >$20,000 per SNF/IRF stay vs near-$0 marginal for home; CJR cut SNF discharge from ~50% to ~10%
*[moderate]*

SNF or inpatient rehab after TKA can exceed $20,000 for the facility stay alone; Medicare SNF benefit: days 1-20 $0, days 21-100 $217/day beneficiary coinsurance (2026 was ~$217.50/day per benefit-period rules — verify current year figure); home health PT is covered 100% under the home-health benefit with no coinsurance. CMS's own CJR participant case studies report hospitals moving from ~50% SNF discharge to ~10%, recovering the rest at home. Every patient safely steered from SNF to home-with-RTM keeps roughly $10,000-$20,000 inside the episode target — the single largest controllable lever in TEAM reconciliation, and the one where continuous monitoring provides the clinical cover surgeons need to discharge home.

> AAHKS hipkneeinfo.org, "Total Knee Replacement: A Breakdown of Costs"; CMS, "Faster, Safer Recovery at Home After Joint Replacement: CJR Model Participant Stories," https://www.cms.gov/priorities/innovation-center/value-based-care-spotlight/patient-provider-voices/primary-care-stories/faster-safer-recovery-home-after-joint-replacement

### Hospital THA/TKA complication measure (NQF #1550): median RSCR 3.6%, range 1.8-9.0%, tied to MS-DRG 469/470
*[strong]*

The Hospital-Level Risk-Standardized Complication Rate (RSCR) Following Elective Primary THA/TKA (NQF #1550, publicly reported on Care Compare, used in Hospital IQR/star ratings and formerly the CJR quality score) counts specified complications in windows anchored to admission: e.g., AMI/pneumonia/sepsis within 7 days, surgical-site bleeding/PE/death within 30 days, mechanical complications and PJI/wound infection within 90 days. Median hospital RSCR 3.6% (range 1.8%-9.0%); most frequent components: pneumonia 0.86%, PE 0.75%, PJI/wound infection 0.67%. Applies to MS-DRG 469 (with MCC) and 470 (without MCC); an IP/OP combined 90-day version is being developed as arthroplasty shifts outpatient. A platform that timestamps complication detection against these exact windows speaks the hospital-quality language natively.

> CMS/NQF #1550 fact sheet (BPCI-Advanced quality measures), https://www.cms.gov/priorities/innovation/files/fact-sheet/bpciadvanced-fs-nqf1550.pdf; Partnership for Quality Measurement measure #1550, https://p4qm.org/measures/1550; CMS IP/OP 90-day THA/TKA Complication Measure Methodology Report

### Outpatient migration: TKA off inpatient-only list 2018, THA 2020; inpatient volumes down 85% (TKA) / 66% (THA)
*[moderate]*

CMS removed TKA from the inpatient-only (IPO) list January 2018 and THA in the CY2020 OPPS final rule; TKA was added to the ASC Covered Procedures List in CY2020 (THA followed in CY2021). Inpatient TKA volume fell 17.9% in year one post-removal and 85.4% from pre-removal baseline; inpatient THA fell 35.8% in year one and 66.1% overall; Trilliant Health estimated ~$5.3B hospital revenue at stake from the shift. Consequence for the platform: same-day-discharge and ASC arthroplasty patients have zero inpatient observation time, making the first 72 hours at home the highest-acuity unmonitored window in the care pathway — and CMS is following with an outpatient/ASC PRO-PM. TEAM explicitly includes outpatient (HCPCS-anchored) LEJR episodes.

> AAHKS CY2020 OPPS/ASC final rule summary, https://www.aahks.org/advocacy/cy2020-opps-asc-pr/; Trilliant Health, "Potential Revenue Impacts of Elimination of the Medicare Inpatient Only List" (2021-2022), https://www.trillianthealth.com/market-research/studies/revenue-impacts-elimination-medicare-inpatient-only-list

### 2026 RTM national Medicare payment rates (non-facility national averages)
*[strong]*

CY2026: 98975 (initial setup/patient education, once per episode of care) ~$22; 98976 (respiratory device supply, 16-30 days of data per 30-day period) ~$52; 98977 (musculoskeletal device supply, 16-30 days/30-day period) ~$40; 98980 (treatment management, first 20 min/calendar month, >=1 interactive communication) ~$54 (0.62 work RVU); 98981 (each additional 20 min) ~$41 (0.61 wRVU); NEW 98979 (treatment management, first 10-19 min/month with >=1 real-time interactive communication) ~$26 (0.31 wRVU); NEW short-duration device-supply codes 98984/98985/98986 (2-15 days of data per 30-day period; the family mirrors RPM's new 99445) ~$51-52 — note conflicting vendor descriptions of which code maps to MSK vs respiratory vs CBT; verify descriptors against the CPT 2026 book/final rule addendum. 2025 comparators: 98975 $19.73, 98977 ~$40, 98980 ~$54. All rates vary by GPCI locality.

> Tenovi, "RTM CPT Codes 2026" (2025), https://www.tenovi.com/rtm-cpt-codes-2026/; CMS CY2026 PFS Final Rule, Federal Register 2025-19787 (Nov 5, 2025), https://www.federalregister.gov/documents/2025/11/05/2025-19787/

### 2026 PFS RTM/RPM policy changes: 16-day threshold broken, billing rules and constraints
*[strong]*

The CY2026 PFS final rule (released Oct 31, 2025) ended the all-or-nothing 16-day data requirement by paying for 2-15 days of transmitted data (RTM 98984-98986; RPM 99445 paid at the 99454 rate) — enabling episodic/acute post-op monitoring where early dropout previously meant $0. Constraints that must be encoded: device-supply codes billable once per 30-day period regardless of number of devices; management codes once per calendar month; cannot bill the 10-19 min base (98979) and 20-min base (98980) in the same month; cannot combine 2-15 day and 16-30 day supply codes; cannot bill RPM and RTM concurrently for the same patient in the same month; only one practitioner bills per 30-day period. CMS adopted CPT's "live, interactive communication" language for the management-code communication requirement without enumerating exclusions. Provider eligibility unchanged (physicians/QHPs; RTM notably billable by PTs/OTs as therapy services). Patient consent must be obtained (may be at time services are furnished) and standard Part B 20% coinsurance applies to every code — a patient-facing cost of roughly $8-11/month that practices must disclose.

> Nixon Law Group, "CMS Finalizes 2026 Remote Monitoring Reimbursement Updates" (2025), https://www.nixonlawgroup.com/resources/cms-finalizes-2026-remote-monitoring-reimbursement-updates-what-changed-for-rpm-and-rtm; CMS CY2026 PFS Final Rule

### Evidence that monitoring platforms move the metrics payers price
*[moderate]*

mymobility RCT (Zimmer Biomet, 828 primary hip/knee patients; 447 control, 381 app+Apple Watch): non-inferior 90-day readmissions with PT visits cut from 9.75 to 5.40 per patient; JMIR 2025 cost analysis reported ~$186/patient net 90-day cost reduction among non-crossovers. Force Therapeutics (vendor-reported, treat as promotional): >26% year-over-year reduction in 90-day TJA readmissions across clients and claimed average savings of $2,100 per MSK episode via reduced outpatient utilization; separate 2024 study claims 30-day readmission reductions. The peer-reviewed core (fewer PT visits, non-inferior safety) is solid; the large per-episode savings claims are vendor marketing.

> "Smartphone-Based Care Platform Versus Traditional Care in Primary Knee Arthroplasty: Cost Analysis," JMIR mHealth 2025, https://mhealth.jmir.org/2025/1/e46047; PubMed 37470176, 36894289; Force Therapeutics press releases (2022-2024), https://www.prnewswire.com/news-releases/force-therapeutics-reduces-90-day-readmissions-for-total-joint-arthroplasty-patients-301471744.html

### The practice's buy-decision math (derived worked example)
*[moderate]*

Per Medicare TJA patient on a 90-day RTM program: 98975 once ($22) + 98977 x3 30-day periods ($120) + 98980 x3 months ($162) + 98981 x1-3 ($41-123) = ~$345-$427 direct billing per patient; patients who stop transmitting early still yield ~$51-52/period via 98984/98985 instead of $0. A 500-TJA/year practice: ~$170k-$210k/yr gross RTM revenue. TEAM-side upside per 100 episodes for a hospital partner: preventing one PJI readmission saves $38,865-$79,223; converting 10 SNF discharges to home saves ~$100k-$200k against target prices that already embed a 2% CMS discount; and each avoided 30-day readmission saves ~$9k-$52k inside the episode. Quality-side: hitting >=50% PRO-PM matched-pair collection protects the FY2028 IQR annual payment update and the TEAM CQS multiplier (up to +10% on gains / -15% relief on losses). Stop-gain caps mean maximum TEAM upside is 10-20% of the reconciliation target amount depending on track.

> Derived from CMS CY2026 PFS rates (Tenovi 2026), Milliman TEAM walkthrough (2025), Arthroplasty Today PJI costs (2022), and CJR evaluation reports; arithmetic is the author's synthesis


## Implications for backend

- Encode the RTM billing calendar as first-class engine state: per-patient 30-day device-supply windows with a transmitted-data-day counter (a calendar day counts once regardless of number of readings), selecting 98977 at >=16 days, 98984/98985 at 2-15 days, and nothing at 0-1 days; separately accumulate clinician management minutes per calendar month with an interactive-communication flag to choose 98979 (10-19 min) vs 98980 (+98981 per extra 20 min), and enforce the mutual exclusions (no 10-min + 20-min base same month, no RPM+RTM same month, one biller per period).
- Anchor the risk engine's complication windows to the CMS measure clocks: PJI/wound infection and mechanical complications scored at 90 days, PE/bleeding/death at 30 days, pneumonia/AMI/sepsis at 7 days from anchor admission (NQF #1550), and a hard 30-day post-discharge window for TEAM episode cost attribution — surface every HIGH-tier alert with its days-remaining-in-episode so the financial stake is explicit.
- Add a PRO-PM compliance subsystem: schedule HOOS Jr./KOOS Jr. capture within 90 days pre-op and 300-425 days post-op, compute matched-pair rate against the >=50% threshold and the >=25-pair minimum, and score each patient against the SCB thresholds (>=22-point HOOS Jr. gain for THA, >=20-point KOOS Jr. gain for TKA) so the platform can report projected PRO-PM performance to hospital partners.
- Build an episode-economics dashboard that multiplies the engine's existing detections into dollars: avoided-SNF conversions at $10k-20k each, flagged-early PJI at $38.9k-$79.2k, avoided 30-day readmission at $9k-52k, avoided MUA at ~$17.5k incremental (revision-for-stiffness delta $65,771 vs $48,287), against a regional TEAM target price computed from a stored 3-year baseline with the 2% LEJR discount.
- Store TEAM-relevant risk-adjustment covariates per patient (age band, HCC-count proxy from intake comorbidities, prior PAC use, dual/LIS status, procedure indicator TKA/THA/partial/ankle) so per-patient expected-cost baselines can mirror CMS's target-price regression rather than a flat average.
- Capture and persist RTM consent (timestamp, method) and disclose the ~20% Part B coinsurance (~$8-11/month) in the enrollment flow; log every interactive communication with duration, since 98980/98979 are unbillable without at least one real-time interaction in the month.
- Prioritize the first 72 hours post-discharge for same-day-discharge/ASC patients in alert sensitivity tuning — outpatient migration (85% inpatient TKA volume decline) means this is the window with no other clinical surveillance and where the readmission-prevention value concentrates.

## Open questions

- What is CJR-X (Comprehensive Care for Joint Replacement Expanded)? A cms.gov model page exists but the fetch was blocked (403) and the search budget was exhausted — determine its start date, voluntary/mandatory status, and whether it targets ASC/outpatient episodes CJR never covered.
- Exact TEAM CQS measure weights and decile point scales per episode type as codified at 42 CFR 512.547 (the fact-sheet PDF was 403-blocked); needed to model how many PRO-PM percentage points translate into reconciliation dollars.
- Definitive CPT 2026 descriptor mapping for 98984/98985/98986 (which code is respiratory vs musculoskeletal vs CBT supply) — vendor sources conflict; verify against the CY2026 PFS final rule addendum B or the AMA CPT 2026 code set, plus the 98978 (CBT device) 2026 rate.
- The precise 2026 SNF Part A coinsurance daily rate (2025 was $209.50; a $217/day figure was quoted in a 2026 consumer source) and current national average SNF episode cost specifically following TJA under PDPM.
- Whether CMS's 2026 dual conversion factors (qualifying APM vs non-APM, ~$33.57 vs ~$33.40) and the efficiency adjustment materially changed the RTM code rates quoted by vendors, and the facility-setting rates for hospital-employed billing.
- Contemporary (2024-2026) national 30-day RSRR for elective THA/TKA under HRRP and the current distribution of HRRP penalties attributable to the THA/TKA cohort — my 4-4.3% recollection was not verifiable within the search budget.
- Whether any peer-reviewed study yet ties RTM (98975-98981 billing specifically) to TEAM/CJR reconciliation outcomes — the ROI evidence is currently PT-substitution and readmission non-inferiority, not bundle-reconciliation deltas.