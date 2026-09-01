# Adversarial Review: Post-Op Monitoring Design

I've reviewed the combined design. It is unusually honest — the adjudication tables, the refusal lists, and the volume gates are better than most Series A clinical products ever produce. That makes the remaining problems harder to see, so I'll be blunt about them.

The document's central weakness is that it is **four documents that never reconciled**. Section 2 ranks phone-inclinometer ROM as the #1 replacement signal for steps in weeks 0–3 and never mentions wound drainage. Section 4-clinical opens by declaring wound drainage the only day-scale signal in the entire corpus. Section 2.3.1 ships composite weights of RHR .25 / temp .25 / HRV .20 / RR .15 / function .15; Section 4.3.2 ships RHR .28 / HRV .24 / RR .20 / steps .16 / temp .12. Both are labeled "the P4 fix." Three separate sections independently correct the same wrong `TIER_ORDER` claim. Nobody owns the whole.

---

## 1. Claims that would not survive contact with a real orthopedic practice

**The de-escalation lane converts non-response into reassurance.** This is the most dangerous thing in the design and it is presented as the business case. `WOUND_DRY_THROUGH_D14` drops infection-pathway precedence to zero and halves check-in cadence. In `clinical/wound.py` it has no denominator gate at all. The Severity-4 `wound_pathway()` gates only `WOUND_CLEAN_30D` on `len(series) >= 21` — the week-2 rules read `wk(8,14)`, which is satisfied by a single answered day. A patient who answers once in week 2 saying "none" is indistinguishable from one who answered seven times. At the design's own cited engagement figure (Bressman 79.5%), the probability of a **complete** dry week 1 is 0.79⁷ ≈ 0.19 — so `WOUND_NEW_ONSET_WEEK2` (OR 80.71, the second-highest rung) is computable on roughly one patient in five, and its denominator is invisible. Every wound rule needs an explicit denominator, an explicit `UNCERTAIN` state, and rendered text of the form "no drainage reported on 11 of 14 days; 3 days unanswered."

**The 83% PPV string violates the design's own device position.** §4.10.1 refuses to ship a PJI probability. The highest-tier surgeon-facing string in the product is `"Moderate drainage, POD 19. Reference PPV 83%."` That *is* a probability of infection, transported from a study with 16 events that the verification pass could not locate, into a cohort with different dressing protocols and a different base rate. §4.1.1 says "never display an odds ratio"; Severity 4 then carries `{"or": 103.23}` in the reason-code payload and renders it. Pick one.

**The navigator tier will not be staffed.** The design's own labor math: 500 active patients × one mandatory real-time interactive call per calendar month ≈ 167 hours ≈ 1.0 FTE, *before any alert review*, against $170–210k gross. A single-site group doing 500 TJA/yr will staff this with an MA at 0.25 FTE, and the WATCH/CONTACT/ESCALATE ladder collapses into "the surgeon gets pinged or nothing happens." **The product must be safe when the middle tier is absent**, because that is the modal deployment. Today, CONTACT-tier codes route to a queue nobody reads, and that is worse than not firing them.

**The ≤3 surgeon-items/day budget is contradicted by the clinical layer.** §4.5.4 sums the *statistical* detectors. Nobody summed the clinical ones: the wound ladder (4 ESCALATE rungs), `ROM_MUA_RISK_PROJECTED`, `RC_ACTIVE_ROM_REGRESSION`, the EVENT step-cliff, the opioid ladder, `VTE_PROPHYLAXIS_MISSED` at **17% population prevalence**, and the CMS window codes. VTE non-adherence alone, at 17% of ~125 concurrent patients over a 14–35 day window, blows the budget by itself. This is the exact failure §4.5.1 diagnoses and then commits.

**Phone-inclinometer ROM is inconsistent across three sections.** §2.7.2 makes it build-first primary. §2.4.3 puts MDC95 gates (extension ≥3.1° — the tightest threshold in the product) in the statement table with no caveat. §4.3.2(c) requires a clinician-confirmed value before ESCALATE. The n=30 study was supervised, and its own note is that all patients "could comprehend and execute the assessment." An unsupervised 66-year-old on POD 5 with a swollen knee produces systematically biased, trunk-compensated segment angles. A 3.1° gate on the noisiest capture channel in the product will manufacture the MUA false positives.

**The 365-day TKA horizon is unfunded and creates a documented expectation you will not meet.** RTM revenue stops ~month 3; TEAM stops at day 30. The design says the tail is funded by the PRO-PM capture at 300–425 days — that's one questionnaire, not nine months of monitoring, and it presumes the app is still installed and the watch still charged. The 42%-of-TKA-PJIs-after-day-90 fact is real and important; shipping a config field that claims to cover it is a liability, not a feature.

**MSIS/EBJIS adjudication is unreachable through the stated pipes.** Synovial WBC, α-defensin, and leukocyte esterase come from an office or OR aspiration — send-out with a local code, or narrative in the op note. Stage 0/1 FHIR gives you `Observation(category=laboratory)` from the reference lab. The PJI labels table will be populated by human chart review, which nobody staffed or costed.

---

## 2. Where the design still assumes signal the research showed is absent

**The 24–36h HealthKit freshness SLA is flatly incompatible with the hours-scale physiologic claim.** §4.0-clinical: the ceiling on physiologic lead time is **14 hours** (weak evidence) to 7–11 hours. §2.5.2: Apple HealthKit background delivery is 24–36h, Health Connect 36h. For the largest device cohort, the data arrives *after* the entire published lead time has elapsed. Add nightly 02:00 batch scoring and business-hours acknowledgment and the expected realized lead time for the physiologic channel is approximately zero. Either state that the physiologic stream is a **trend instrument with no acute claim**, or drop Apple. You cannot hold both statements.

**The composite index should not exist in weeks 0–4.** The design demolishes each input individually: steps suppressed POD 0–28 unconditionally; sleep weight zeroed (wake specificity 29–52%); SpO2 removed; skin temp demoted with the design's own arithmetic showing a 0.4 °C ambient excursion yields z ≈ +3.3; RR carrying 0.15–0.20 weight on a metric for which **no validation figure was retrievable**; HRV with LOA ±11–15 ms and vendor sampling contracts that are non-comparable by construction. With `MIN_WEIGHT_PRESENT = 0.60` and steps suppressed, the modal early composite is RHR + HRV + RR — three correlated channels triple-counting one autonomic disturbance, one of which is unvalidated. The honest conclusion the design refuses to draw: **for POD 0–28 there is no usable multivariate physiologic composite.** Ship a single nocturnal RHR trend.

**Walking speed as a per-patient signal.** A4 correctly notes the 6-week nadir is 0.11 m/s against a median MDC of 0.14, and prescribes 7-day means. But §4.2.3 establishes lag-1 autocorrelation of 0.4–0.7 on daily wearable series. At φ = 0.5, seven days gives an effective n ≈ 2.3, so the SE falls by ~1.5×, not 2.6×: 0.14 / 1.5 ≈ 0.09 against an effect of 0.11. You are resolving a population-level effect at ~1.2 SE. Walking speed belongs with sleep duration: display-only, weight zero.

**LifeSnaps does not give you a post-op specificity estimate.** It is 71 non-surgical adults. The post-op *null* — uncomplicated recovery — has RHR elevated 10–15 bpm, disrupted sleep, opioids, anemia, and a legitimate six-week activity nadir. Thresholds calibrated on a healthy free-living null will fire on essentially every uncomplicated patient in weeks 1–3. §4.3.3(3) proposes conformalizing residuals against the fitted expected curve to fix this — but that curve is `hand_tuned_v0` until 20–30 patients exist. The mitigation depends on an artifact that does not yet exist. LifeSnaps is an upper bound on healthy-state specificity and nothing more; stop describing it as "the only specificity number you can get."

**Return-to-baseline activity, AUROC 0.76 for 30-day readmission.** At a 3.3–4.5% base rate, 0.76 AUROC does not reach the specificity needed for any usable PPV — the design's own PPV table proves this two sections later. It sits in the complication registry as the watched signal for readmission. Delete it.

**The wound ordinal is protocol-dependent in a way that breaks the week-2 shape.** A practice using a 14-day occlusive waterproof dressing produces *zero* drainage reports in week 2 because the patient cannot see the wound — and there is no "didn't look" option in the 5-point scale. "Moderate vs heavy" as a patient-graded ordinal has no anchor. The one operationalized definition in the whole ladder — ICM `dressing_area_gt_2x2cm` — is the only rule *not* derived from the n=1,019 study. Ship the 2×2 cm rule and a binary any/none. Hold the moderate/heavy rungs until locally re-derived.

**The 0–4 wear-evidence score has anticorrelated failure modes.** A night-only wearer scores 3 and passes, with meaningless steps and fine nocturnal RHR. An all-day-wear/charge-at-night patient fails `NO_VALID_NIGHT`, loses 2 points, and is gated out of the RHR/HRV statements — the only ones that work for them. The per-statement minimums in §2.4.3 are right; the single scalar feeding `VALID_DAY_MIN_SCORE` is wrong and should be deleted.

---

## 3. Where the product is silent while a patient deteriorates

**The modal PJI presentation is a blind spot.** Median POD 14 (IQR 10–18), walker still in use, no pre-op baseline (41% completion per the design's own field citation), Apple Watch. Steps: suppressed. Composite: RHR + HRV against a population prior with `B_n = 0`. Wound channel: patient stopped answering. The loudest output the product produces is `DATA_LOSS_DISENGAGEMENT` at MEDIUM, into an unstaffed queue.

> **Fix:** loss of the *wound* channel during POD 7–21 is not the same event as wearable coverage collapse and must not share a tier. It should open a CONTACT episode with a mandatory human call, week-conditioned. Right now both are the same undifferentiated class.

**Population-prior mode is a near-mute detector, not graceful degradation.** Between-person SD runs 2–3× within-person SD. A patient with a genuine sustained 3 bpm RHR rise — their own 3σ — sits at roughly 1σ population and never fires. With 41–59% of the panel in this mode, the product should say **"physiologic monitoring is not active for this patient; wound and pain channels only"** rather than surfacing a tier at all.

**Overnight, structurally.** Quiet hours, 09:00–10:00 check-in send, 02:00 batch, business-hours ack. Acute PJI, PE (median POD 3), and dislocation do not observe this. The `not_watched: OVERNIGHT` manifest entry is right, but a footer cannot undo a behavioral affordance — the design itself notes that a bot replying instantly "behaviorally teaches patients that someone is watching." **Suppress all acknowledgment templates outside staffed hours.** Let an unacknowledged message visibly stay unacknowledged.

**PE.** 80% of CT-confirmed post-TKA PE is asymptomatic; SpO2 has MAE 2.2–5.8% with 11–31% failed reads and a 19-month US regulatory gap. The product is and will remain silent. The right response is not a detector: it is a **week-conditioned scheduled safety message delivered at POD 2–7**, when risk peaks — deterministic, free, unregulated, and higher-value than any physiologic detector shipping in year one.

**The EVENT step-cliff detector is a demo feature.** A patient who dislocates is in the ED that day. The ADT feed tells you with high specificity; the step cliff adds nothing and cannot fire during the POD 0–28 suppression window (the design never says whether EVENT is exempt). The design calls ADT "the highest-specificity signal available to this product and cheaper than anything else in this section" — and then schedules it at P1/Stage 2. That ordering is wrong.

**Delirium** (13.6% pooled, POD 1–3, 42.3% in frail patients) requires a caregiver who is not in the data model, and minute-level data gated at ≥1,000 patient-days. Silent.

**What the product should say about all of this:** the reassuring statement must be *structurally* impossible below per-channel evidence, not merely down-weighted — "Stable" should require ≥5 of 7 valid nocturnal windows **and** ≥5 of 7 check-in responses **and** no wound-channel gap >2 days. Below that the string is "not enough information to say." Every de-escalation prints its denominator. And the enrollment teach-back names the four blind spots explicitly: overnight, dislocation, clots, and anything you don't tell us.

---

## 4. The single most likely reason this fails — and the cheapest experiment

**Most likely failure:** the wound/symptom check-in is the only channel in the entire design with day-scale lead time and defensible discrimination. It is also the channel that decays fastest, is denominator-fragile, and is not reimbursed at a level that funds a human to chase non-responders. The product will silently convert non-response into reassurance, the de-escalation lane will look like it is working, and the first missed PJI will be a patient the product had classified as low-yield. This failure is invisible in a demo and invisible in seed data, and it is not a statistics problem — no amount of PEB, conformal calibration, or episode-state-machine work touches it.

**Cheapest experiment (2 weeks, ~$3k, zero engineering, no product):** a 30-patient / 30-day SMS wound-capture feasibility study at one partner practice. One question a day: *"Any drainage on your dressing today? None / A little / A lot / Didn't look."* Scheduling tool plus a spreadsheet. Measure only four things:

1. Daily response rate by post-op day, stratified by age band and by dressing protocol.
2. The fraction of patients with a **complete** week 1 and a **complete** week 2 — the denominators the OR-80.71 and 88/88 rules require.
3. The share answering "didn't look" — a response the current 5-point ordinal has no slot for, and which under an occlusive dressing is plausibly 30–50% of week-1 answers.
4. Same-day test-retest of the ordinal, 6 hours apart, on 10 patients.

If daily completion lands at 55% with 40% "didn't look," the entire precedence-0 pathway must be rebuilt around a **weekly structured photo plus three questions** rather than a daily ordinal — and you learn that before building the ladder, the phrasing library, the PPV ledger, and the navigator workflow on top of it.

Run in parallel, one afternoon of email: ask three practices for the distribution of scheduled-surgery-to-surgery intervals, stratified inpatient vs ASC. That number decides whether the personal-baseline architecture is viable at all.

---

## The three things I would do first

1. **Run the 30-day wound-capture feasibility study before writing another line of the clinical layer.** Every precedence-0 rule, the de-escalation lane, and the navigator economics all rest on a per-day denominator nobody has measured. It is the cheapest, fastest, most load-bearing unknown in the plan.

2. **Cut the composite index and the multi-metric physiologic story out of v1.** Ship four things: nocturnal resting-HR trend (single metric, one conservative CUSUM, personal baseline or nothing); the wound/pain check-in with explicit denominators and an `UNCERTAIN` state; the PT magic-link ROM form; and the ADT feed. Everything else — HRV, RR, skin temp, SpO2, walking speed, sleep, steps — is display-only and labeled exploratory. That is roughly 20% of the engineering in this design and it is defensible line by line. The remaining 80% is currently building precision on top of channels the document itself proves are too weak.

3. **Buy the ADT feed and ship the outcomes/adjudication schema in the same sprint.** ADT is the only high-specificity signal in the product and the only one with an outcome label attached; it is a CMS Condition of Participation your customers already qualify to receive. The outcomes schema has a two-year lead time and the clock starts the day it ships, not the day you decide you want a model. Without both, this is permanently a monitoring instrument that can never prove it works — which is a survivable position to *ship* from, but not one to raise money on.