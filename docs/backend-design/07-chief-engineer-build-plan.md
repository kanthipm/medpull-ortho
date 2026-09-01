# Chief Engineer's Adjudication and Build Plan

**Basis:** the four design sections plus direct inspection of the codebase at `/Users/steve/Documents/GitHub/MedPullKioskKanthi/recovery-copilot/backend/`. Where a section makes a claim about the code, I checked it. Several claims are wrong and several defects nobody found are listed below.

**Today is 2026-07-31.** That date is load-bearing and no section connected it to the calendar: the Fitbit Web API sunsets **September 2026**, i.e. inside this 90-day window. See Contradiction 12.

---

## Part 1 — Contradictions, gaps, and adjudications

### 1A. Cross-section contradictions

---

**1. Four documents disagree about what the primary signal is, and the build plans are mutually exclusive.**

- *Data section:* steps demoted; ROM #1, pain/adherence #2.
- *Clinical section:* wound drainage is a precedence-0 pathway that sets tier alone; vitals are "corroboration only," lead time hours not days.
- *Statistics section:* the entire architecture — PEB baselines, Kalman, composite, conformal, trajectory — is built on the six-vital composite as the product.
- *Completeness section:* the composite has 0.55 of its weight on device artifacts; text is the primary instrument.

**Adjudication: clinical + completeness win, and this reorders the statistics section's entire sprint plan.** The evidence is not close — days versus hours. Consequences the statistics section must absorb, and did not:

- The composite is a **corroborator that adds specificity to a wound/pain flag**, not the tier originator. It stops being the thing that must be perfect before launch.
- The coverage gate must be **text-first**: a patient with a flawless Apple Watch stream and five days of check-in silence is LOW confidence, not HIGH coverage. Today `app/engine/confidence.py:KEY_METRICS` contains six wearable metrics and no patient-reported channel at all.
- Sprints 2–5 of the statistics plan (PEB, Kalman, transforms, trajectory) drop out of the first 90 days entirely. They are refinements to the corroborator.

---

**2. Three incompatible composite weight vectors, none of which has an author.**

| Source | RHR | Skin temp | HRV | RR | Function |
|---|---|---|---|---|---|
| Shipped code (`app/engine/composite.py:14`) | .25 | .25 | .20 | .15 | .15 |
| Statistics §4.3.2 | .28 | .12 | .24 | .20 | .16 |
| Data §2.3.1 `FAMILY_WEIGHTS` | .25 | .25 | .20 | .15 | .15 |
| Completeness §14 | — | demote | — | **.05** | gate on aid |

**Adjudication: none of them ships as authored.** The statistics section is right that the weights must be elicited (§4.3.5) and right to demote skin temp; the completeness section is right that RR carries 0.15–0.20 on a channel whose own corpus says "respiratory rate validation numbers for consumer wearables were not retrievable." Interim vector until elicitation: **RHR .30 / HRV .25 / skin temp .20 / steps .20 / RR .05**, with `RR_UNVALIDATED_CHANNEL` in the basis panel. The elicitation session is a founder calendar item, not an engineering task (Part 3, #7).

---

**3. The composite's minimum-weight gate has never been checked against the device mix, and for common devices it can never compute.**

Both `MIN_WEIGHT_PRESENT = 0.60` (statistics) and `available_weight ≥ 0.60` (data) are asserted without the device × metric availability matrix. Work it: a Garmin patient with no wrist temperature and no vendor RR loses skin temp (.25) and RR (.15) = 0.60 available before steps suppression; suppress steps (§2.2.2) and they are at **0.45 — permanently below the gate**. The composite structurally never fires for that patient, and nothing in the design notices, because the gate emits `insufficient_metrics` silently rather than escalating.

**Adjudication: build the matrix before shipping the gate** (1 engineer-day, listed in the plan). Then either (a) set the gate per device family, or (b) make persistent gate failure itself an alertable state — a patient we structurally cannot score is a patient nobody is watching, which is the exact failure the coverage gate exists to prevent.

---

**4. Steps are suppressed in the window where every step-based detector is supposed to fire.**

- Data §2.2.2 suppresses steps for POD 0–28 unconditionally **and** whenever the aid is in `{WALKER, ROLLATOR, CRUTCHES_*, WHEELCHAIR, UNKNOWN}`. §2.1.5 defaults POD 22+ to `UNKNOWN`, which is itself a suppressing aid. **With no aid capture, steps are suppressed forever.**
- Statistics §4.4 builds the whole trajectory layer on the step ratio.
- Clinical §4.2.1 puts the dislocation and periprosthetic-fracture EVENT detector on a same-day step cliff — and 91% of posterior-approach dislocations occur within 6 weeks, i.e. inside the suppression window.
- Clinical §4.3.2 uses week-1 and week-6 step counts as TKA milestones.

**Adjudication, three parts:**
1. **Aid capture is a hard dependency of the entire functional layer**, not a 3-day nice-to-have. It must land with the first check-in form or steps are dead.
2. `UNKNOWN` must not suppress the same way `WALKER` does. Split: `UNKNOWN` suppresses *trend* contribution but permits display and event detection. Otherwise the default state of the system is blindness.
3. **Carve an explicit EVENT-class exemption into `steps_gate.py`.** A −70% same-day cliff is not producible by the aid artifact (adopting an aid you already have cannot halve your count in one day; dropping one causes a *jump*). The gate currently returns a flat boolean and cannot express this.

---

**5. The trajectory layer, as specified, produces nothing during the window the buyer pays for.**

Compose the constraints: no trajectory reason code before POD 7 (stats §4.4.5) + steps suppressed to POD 28 (data §2.2.2) + individual curve parameters need ≥10 of the patient's own days (stats §4.4.3) → **first trajectory statement lands around POD 38.** The CMS TEAM episode ends at **day 30**. PE peaks POD 2–7. Dislocation is 91% within 6 weeks. The MUA decision window closes at week 6.

**Adjudication: the step-trajectory layer is Phase 2, after the 90 days.** The day 0–28 functional signal is (a) clinic- and app-measured ROM, (b) walking-bout minutes where the provider exposes them, (c) the pain curve. The one trajectory feature that ships early is the **MUA flexion projection**, because it fires POD 21–35 with runway — and it runs on ROM, not steps.

---

**6. Three replacements are specified for `curves.py`, and nobody noticed that `deviation.py` imports it into the live scoring path.**

Verified: `app/engine/deviation.py` imports `curve_mid` from `app/engine/curves.py` and divides all FUNCTIONAL metrics by it. The seed generator imports the same function. **Severing the `app.seed → app.engine` edge (P5) therefore does not remove the circularity from scoring — it only removes it from the tests.** The unfalsifiable curve is still the denominator of every functional z-score in production.

Worse, and caught by no section: `FUNCTIONAL = {M.STEPS, M.WALKING_SPEED}` and **both are divided by the same `curve_mid`**. Steps recover ~4.4× from week 1 to week 20 (1,439 → 6,344). Walking speed dips 21.8% and returns to baseline at week 21. These are different shapes, different scales, and different units of "fraction of pre-op capacity." Using one curve for both is a category error live in the code today.

**Adjudication:** clinical's milestone `ProcedureClock` and statistics' `expected_curve` artifact table are compatible if layered — milestones are deterministic gates, the artifact is the continuous band. But `curves.py` must be **deleted as a scoring dependency**, not "kept for ankle/meniscus," and walking speed gets its own reference or is scored against the patient's own 7-day trailing mean with no curve at all.

---

**7. Four incompatible specifications for the coverage/confidence gate, including one that says to delete it.**

Shipped: ≥3 of 6 key metrics on ≥40% of 7 days. Data §2.4.3: two-stage with a per-statement-class table. Statistics §4.5.3: raise to 5 of 7. Statistics §4.1.1: *"the coverage gate collapses into `B_n`."* Completeness §5: coverage **residual** against an expected wear-decay prior, not coverage level.

**Adjudication: statistics §4.1.1 is wrong and the error matters.** `B_n` measures how much of a patient's *baseline* is their own — a pre-operative property. Coverage measures whether we can see them *this week* — a current-window property. A patient with 30 pre-op days (`B_n` ≈ 0.9) who has not worn the watch since Tuesday scores as maximally personalized and entirely unobserved. These are orthogonal and both must ship. Final gate = per-statement-class minimum data (data) **×** coverage residual vs decay prior (completeness) **×** text-channel presence (adjudication 1).

---

**8. Sleep duration is declared untrustworthy for clinical use and then made load-bearing for the validity gate.**

Data §2.3.4 sets its composite weight to 0 (wake specificity 29–52%, TST bias up to +40 min). Data §2.4.2 then awards **2 of the 4 wear-evidence points** for `sleep >= 4.0` hours with a ≤30 min gap — so the metric we do not trust governs `valid_day`, which governs the regulatory posture.

**Adjudication: this is acceptable but only if the semantics change.** The wear proxy must consume "a sleep *record exists* with plausible bounds" — evidence the device was on the wrist overnight — not the duration *value*. One-line difference in code, and it is the difference between a defensible presence signal and an undefendable physiologic one. Write it that way.

---

**9. SpO2 is simultaneously removed from the coverage gate and made the primary PE detector.**

Data §2.3.3 and statistics §4.5.3 both drop it from `KEY_METRICS`. Clinical §4.2.1 makes it the first moving signal for PE, "weighted maximally POD 0–7." Clinical §4.10 then notes 80% of post-TKA PE is asymptomatic and the wearable MAE is 2.2–5.8% with 11–31% failed reads.

**Adjudication: not actually contradictory, but the design never says so.** Remove from the *coverage gate* (its absence is a regulatory/device artifact, not non-adherence). Keep as a *detector input* at derated weight, never sole basis for a tier, with `SPO2_UNAVAILABLE_REGULATORY`, and the skin-tone limitation stated on the model card. Also verified: `app/engine/confidence.py:15` still lists SPO2 — the fix is real, unshipped, and one line.

---

**10. `TIER_ORDER` is corrected three separate times. It was never broken.**

Verified: `app/api/worklist.py:14` reads `{HIGH:0, MEDIUM:1, MISSING_DATA:2, LOW:3}`. Data §2.0, statistics §4.5.3, and completeness §5 each independently rebut a phantom claim.

**Adjudication:** delete the correction from all three documents. The signal here is that the corpus has been reviewing itself rather than the code, and that is a process defect worth naming.

**Meanwhile, a real defect nobody found:** data §2.2.3 states walking asymmetry and double-support are "ingested and shown to clinicians labelled exploratory; neither enters tier logic." Verified false. `app/engine/pipeline.py:33` includes `M.WALKING_ASYMMETRY_PCT` in `ANALYZED_METRICS`, and `app/engine/risk.py:79` emits `GAIT_ASYMMETRY_HIGH` at **severity 2** from an absolute-threshold rule. Asymmetry is in tier logic today, on a metric validated only on 51 able-bodied adults in a locked knee brace. Remove it.

---

**11. Two incompatible bitemporal schemas for the same table.**

Data §2.1.3: append-only with `superseded_at` / `supersedes_id` / partial unique index on `dedupe_key WHERE superseded_at IS NULL`. AI §4.9.5: `revision_seq` with "current = max(revision_seq)" views.

**Adjudication: data §2.1.3 wins.** A partial unique index is enforced by the database; a `max(revision_seq)` view requires a window function on every read of the hottest table in the system and enforces nothing. Ship one schema, once, during the Postgres migration — retrofitting bitemporality later is the expensive version of this decision.

---

**12. The Fitbit sunset is inside the build window and nothing in the plan is dated against it.**

Data §2.5.1 correctly identifies the September 2026 sunset as the strongest argument for an aggregator. Junction integration then sits in **P1, "next quarter."** Today is 2026-07-31. Next quarter is after the sunset.

**Adjudication: the aggregator contract is a day-10 founder deadline and the connector is a Wave-2 blocking item.** Any Fitbit patient on the platform loses their data mid-plan. Also correct in §2.5.1 and worth restating in code: a Fitbit device moving from `dev.fitbit.com` to the Google Health API is the **same device epoch with a new `api_channel`** — the hardware did not change and the baseline must not reset. That single rule prevents a fleet-wide re-baseline on cutover day.

---

**13. Three "change types" (device / firmware / API channel) have three different responses, only partially specified, and two of them contradict each other.**

Data §2.1.2: new device epoch → reset EWMA/CUSUM, supersede baseline, **"do not attempt a conversion factor."** AI §4.9.4: firmware change → 3-day suppression **plus an additive offset** re-estimated as `median(new days 1–7) − median(last 14 pre-change days)`.

**Adjudication: data wins. Refuse the offset.** It assumes the patient is clinically stable across the change window, which is precisely what you cannot know — a patient whose RHR rose 6 bpm because of a developing infection during a firmware push gets that 6 bpm subtracted out permanently. Use suppression plus warm-up.

The gap that remains, and it must be built as an explicit matrix: Apple moved SpO2 computation to the paired iPhone in watchOS 11.6.1, which changes the HealthKit **source device**. Under a naive epoch rule that creates a new epoch and resets every Apple patient on one day. Needs a change-type → response table with a `SOURCE_DEVICE_RENAMED` case that is a no-op.

---

**14. `dedupe_key` includes `device_epoch_id`, which is a database autoincrement.**

Data §2.5.2 makes the key `sha256(provider | device_epoch_id | external_id | ...)`. `device_epoch_id` is assigned by the database at ingest. The key is therefore **not computable from the payload**, depends on a lookup that can race under the per-patient FIFO consumer, and changes if epoch assignment is ever corrected. Nothing specifies how an incoming observation is mapped to an epoch, or what happens to backfill that predates the first epoch record.

**Adjudication:** epoch resolution must be a **deterministic pure function** of `(provider, device_model, firmware, wear_location, effective_start)` against the epoch table, with a synthetic `UNKNOWN_EPOCH` bucket for pre-first-epoch backfill, and the key must use a stable natural epoch key (provider + device_model + started_at), not the surrogate id.

---

**15. The specified statistics code does not run.**

Three defects in `shrunk_baseline` / `_huber_scale` as written in statistics §4.1.8:

- The `n == 0` branch returns a key named `sd_alert` (with the no-op expression `Z_PRIMARY * sigma_pop / Z_PRIMARY`) while the `n > 0` branch returns `sigma_alert`. **Every consumer reading `sigma_alert` raises `KeyError` for every patient with no pre-op data** — which, per completeness §1, is the common case.
- `_huber_scale` calls `_std_norm_cdf` and `_std_norm_pdf`, which are never defined; scipy is banned from the artifact (verified: `infra/build-lambda.sh` excludes scipy and hard-fails if `app/` imports it).
- `β` is a constant given `c=1.345` and is recomputed inside the iteration loop.

**Adjudication:** this is illustrative pseudocode presented as shippable. Treat every code block in the corpus as a specification, not an implementation, and budget review time accordingly.

---

**16. The Kalman filter is initialized in the wrong units and double-corrects for autocorrelation.**

Statistics §4.2.4's `local_level` works in units where `σ_ε = 1` (see `F = P + 1.0`) but is told to initialize `P0 = sigma_alert²`, which is in the metric's raw units. And §4.2.6's parameter block lists **both** the AR(1)-inflated `L_eff` **and** the Kalman innovations simultaneously — but whitening the series and then inflating the limits for autocorrelation is correcting the same thing twice, which pushes the false-negative rate up invisibly.

**Adjudication:** standardize observations before the filter (`P0 = 1`, or work in z-units throughout), and make `L_eff` inflation and Kalman **mutually exclusive**, selected by the Ljung-Box gate the section already specifies. The section says this in prose in one place and contradicts it in the parameter block; the parameter block is what engineers copy.

---

**17. The conformal calibration plan violates the design's own cross-brand rule.**

Data §2.1.2 and §2.3.5: never mix brands in one control chart, no cross-brand conversion, a device change is an episode boundary. Statistics §4.3.3 and completeness §14 then propose calibrating the composite thresholds — replacing `HIGH=2.0` / `ELEVATED=1.2` with empirical quantiles — on **LifeSnaps (n=71, Fitbit Sense only)** and applying them to Apple, Oura, Garmin and WHOOP patients.

**Nobody noticed.** The design forbids exactly this transfer everywhere else.

**Adjudication:** LifeSnaps calibration is valid **only for Fitbit-family epochs**. For every other brand it is a directional false-alarm-rate *estimate*, not a calibration, and it may not set thresholds. The replay is still the single highest-value free experiment in the plan — it tells us our specificity is bad — but it cannot ship as `threshold_source: lifesnaps_empirical_q` across the fleet.

---

**18. Three alert budgets in three units, differing by 13×.**

| Source | Budget | Normalized |
|---|---|---|
| Statistics §4.5.4 | ≤0.5 false **episode openings** / patient-month | 0.5/pt-mo |
| AI §4.9.2 promotion criteria | ≤1.5 **alerts** / patient-week | ~6.5/pt-mo |
| Completeness §6 | ≤3 **surgeon-facing items** / clinic day | fleet-level |

**Adjudication: they measure different objects and must be restated as one ladder, and the missing one is the one that matters.**

- Episode openings: ≤0.5 / patient-month (statistics is right; pin it in CI).
- Surgeon `ESCALATE`: ≤3 / clinic day (completeness is right).
- **Navigator `CONTACT`: budget unset by anyone, and it is the P&L.** Completeness §9 computes that the mandatory monthly interactive call alone consumes ~1.0 navigator FTE at 500 patients. The wound ladder's `WOUND_ANY_WEEK2` rule fires on 12% of *uncomplicated* patients. Nobody costed the ladder in navigator-minutes. **This is a founder decision expressed as an engineering constraint** (Part 3, #6).
- AI's 1.5/patient-week is wrong against all three. Delete it.

---

**19. "The product may not ship a PJI-specific alert" versus a wound rule with published PPV 83% for PJI.**

Statistics §4.5.5 issues a blanket prohibition from the PPV arithmetic. Clinical §4.1 ships `WOUND_MODHEAVY_WEEK3` at `ESCALATE` with its PPV 83% rendered to the clinician.

**Adjudication: clinical wins, and the statistics prohibition must be scoped.** The arithmetic in §4.5.5 is correct *for wearable-derived signals* — that is where PPV can never clear 20% at a 1% base rate. The wound channel is not a wearable; it is a patient-reported observation with an 88/88 operating characteristic. The prohibition should read: *no PJI-specific alert may be raised from physiologic wearable data alone.* The wound ladder is exempt on three conditions the clinical section already imposes — provisional grade, NNE printed, and the alert's *subject* is "wound drainage pattern," never infection.

---

**20. The wound pathway bypasses the composite but the episode state machine cannot represent it.**

Clinical §4.1 routes wound outside the composite (correctly — a 0.15-weight z-score would convert the best rule in the literature into a subordinate clause). But statistics §4.5.2 keys `alert_episode.dedup_key` on `(patient_id, metric_family, direction)`, and wound has neither a metric family nor a direction. A patient with persistent drainage trips 4–5 codes across the ladder (`PWD_GT3D`, `ANY_WEEK2`, `MODHEAVY_WEEK2`, `CUM_GT5_DAYS`, `MODHEAVY_WEEK3`) with nothing to absorb them.

**Adjudication:** generalize the dedup key to `(patient_id, pathway, direction)` where pathway ∈ {wound, vitals\:autonomic, function, pain, coverage}. Wound is one pathway, one episode, tier-escalating. This is a 30-minute schema decision that has to happen before the ladder is written, not after.

---

**21. "Never more than one patient task per day" versus four sections each adding "one cheap question."**

Clinical §4.7 rule 4 and §4.1.2 ("once daily, one question"). Then: pain NRS + exercises + medication + rotating item (clinical §4.7.2), wound drainage (§4.1.2), assistive-device tap (data §2.1.5), subjective sleep quality (clinical §4.4.5), therapy adherence and exercise reps (data §2.2.3). That is 7–8 items, and the evidence cited for the constraint is that thrice-daily task compliance runs 32.3% versus 52.4% once-daily.

**Adjudication: "one task" means one session ≤60 seconds, and the item budget must be owned by one person and fixed.** My allocation for POD 1–14: **4 taps** — pain NRS, wound drainage ordinal, assistive device, exercises done Y/N — with sleep quality and the rotating item alternating into a 5th slot. Everything else moves to weekly or is inferred. Reading level runs in CI at grade ≤6 per AI §4.7.2; that is a build gate and I am keeping it.

---

**22. Patient-facing wound messages cross the AI section's own FDA bright line.**

AI §4.6.4: no software-generated recommendation may reach the patient without a named clinician reviewing and sending it. Clinical §4.7.1 defines `patient_line` per reason code — *"Your care team wants to look at your incision today — please expect a call"* — which is a software-generated, analysis-triggered patient communication.

**Adjudication: `patient_line` is a draft, never auto-sent.** It populates the navigator's send-with-one-click control. The only auto-sent patient text is the AI section's static safety tier (911/practice), which is standing safety instruction and not analysis — and that carve-out survives only because it involves no scoring.

---

**23. The ingestion topology, the store, and the concurrency limit cannot all be true at once.**

Data §2.5.2 designs SQS FIFO with `MessageGroupId = patient_id` for per-patient ordering. Statistics §4.7.4 says set batch concurrency to **1** "while the store is a whole-file SQLite database synced under a global S3 lock." AI §4.8.2 says the SQLite-on-S3 store must be replaced **before the first patient**.

Verified in `infra/cloudformation.yaml:230-231`: `S3_DB_KEY: db/recovery.db`, `S3_LOCK_KEY: db/recovery.db.lock`, `LOCK_TTL_SECONDS: 900`.

**Adjudication: AI wins, and it is the single most blocking item in the plan.** Per-patient FIFO parallelism is meaningless at global concurrency 1. A write collision that silently discards a febrile check-in is a safety defect, not a performance one. **Postgres precedes the ingestion topology, and neither ships behind concurrency 1 with real patients.** Also: the nightly job design differs (statistics: one 900s function enumerating the roster; AI: EventBridge → SQS fan-out → workers). AI is right — a single function at 1,000 patients × 0.5–1s overruns 900s before any LLM call.

---

**24. `MIN_ADJUDICATED_EVENTS_FOR_SUPERVISED_FIT` is 100 in two sections and 30 in another.**

Statistics §4.6 and AI §4.1.2 both set 100, both citing Riley. Completeness §"Gated on volume" sets Platt recalibration at ≥30–50 events and a pooled-logistic hazard at ≥30 events / 3 parameters.

**Adjudication: 100 for anything that produces a number a clinician sees.** Riley's own examples range 4.84 to 23 events-per-parameter; 30 events for 3 parameters is 10 EPP, which the statistics section explicitly demolishes as "not conservative-but-safe, it is the wrong functional form." Completeness loses. Intercept-only recalibration-in-the-large (1 degree of freedom) at ≥30 events is the only concession I will make, and it must be labeled as such.

---

**25. Shadow-mode gating, taken literally, makes the 90-day plan unshippable.**

Statistics §4.8 and AI §4.9.2: *every* engine version, "including parameter-only changes to EWMA L, CUSUM h, or composite weights," ships in shadow first with ≥90 days, ≥30 completed episodes, ≥5 high-tier events. The plan below contains a dozen parameter changes.

**Adjudication: shadow gating begins at the first enrolled patient and applies to changes after the v1.0 baseline is frozen.** Before enrollment, the gate is golden tests + LifeSnaps/PMData replay + the alert-budget CI test. Say this explicitly or the plan blocks itself on day 1.

---

**26. Non-index surgical events get three different reset semantics, and one of them breaks billing.**

Data §2.1.4: POD computed against `is_index` only; functional baselines reset; vitals **not** reset; trajectory suspended 14 days. Completeness §3: blanket baseline invalidation, borrowed-prior mode, 14 days low-confidence — and `postop_day` becomes a function of `MAX(event_date)`. Statistics Sprint 1: `surgical_event` table "so a contralateral procedure resets `postop_day`."

**Adjudication: data §2.1.4 wins outright.** Resetting `postop_day` on a contralateral procedure would restart the RTM 30-day supply period, corrupt the CMS PRO-PM 300–425 day post-op window, and reset the surveillance horizon on the *index* joint whose infection risk is what we are monitoring. Completeness's blanket vitals reset is wrong for the reason data gives: a contralateral surgery genuinely perturbs RHR/HRV/temp, and that perturbation is clinically real.

Adjacent gap nobody wired: CMS PRO-PM excludes **staged procedures**, so `surgical_event` must feed the PRO-PM eligibility state machine.

---

**27. The MUA projection, the highest-dollar alarm in the product, imports a banned library and depends on a data channel nobody budgeted.**

Clinical §4.3.2's `projected_week6_flexion` calls `scipy.stats.theilslopes`. Verified: `infra/build-lambda.sh` line ~41 greps `app/` for scipy imports and exits 1. This PR fails the build the day it lands.

Worse: clinical §4.3.2 adjudication (c) requires a **clinician-confirmed** ROM value before `ESCALATE`, while data §2.7.2 says build phone-inclinometer ROM first. Both cite the same PLOS One n=30 study.

**Adjudication:** hand-roll Theil–Sen (median of pairwise slopes over ≤10 points is ten lines of numpy) or compute it in the nightly job. And the two ROM positions reconcile as: **phone ROM may open an episode at CONTACT and drive the early projection; a clinician-measured value is required before ESCALATE.** Which means completeness §2's **PT magic-link form is a dependency of the MUA feature, not a nice-to-have.** The alarm with the clearest dollar value ($65,771 vs $48,287 revision cost) needs a data channel that appears in exactly one of five sections and in no budget.

---

**28. The AI section bans LLMs from the runtime path and then puts a 770M-parameter model in the Lambda.**

AI §4.4.2 makes MiniCheck-FT5 gate G4 with "200–800 ms warm" latency, ~1GB at int8. AI §4.8.3 measures the artifact at 150–190MB against a hard 250MB unzipped ceiling and notes layers do not help.

**Adjudication: G4 cannot ship in the Lambda, ever.** G1–G3 are pure Python and belong inline. G4 is a nightly batch scorer or it does not exist. The section says both things and engineers will implement the wrong one.

---

**29. The Groq BAA is treated as a hard launch blocker when the design's own option C removes the need for it.**

AI §4.5 declares the free-tier Groq path illegal for PHI and gates the roadmap on the BAA. Option C — the PHI-free prompt serializer emitting tier + reason codes + z-scores + *relative* post-op day, with no name, DOB, MRN, calendar date, device serial, or raw series — is dismissed as "defense in depth, not a substitute for the legal position."

**Adjudication: the corpus is over-cautious in a way that costs weeks on the critical path.** If the serializer is rigorous and enforced by the egress flag, there is no PHI egress and no BAA is required for that path. The re-identification finding the section cites (Na 2018, 94.9% from 20-minute-aggregated accelerometry) is about **time series**, and the serializer emits no series. Get the BAA — it is days of legal work and it buys optionality — but **do not let it block the build.** Ship the serializer + egress flag as the enforceable control.

Related, and correct: the Ollama leg in `app/llm/provider.py` is a second uncontrolled egress destination. Verified present. The egress flag's `test_ollama_is_never_covered_for_phi` is the right encoding.

---

**30. "Bill no 9897x codes" versus a commercial model entirely built on RTM revenue.**

AI §4.6.6(3) suspends all RTM billing pending a written coding-and-coverage opinion on the §201(h) bifurcation. Clinical §4.8.3 builds the three-legged pitch on $345–427/patient of direct RTM billing.

**Adjudication: AI wins on sequencing. The founder must get that memo in weeks, not months** — it is the revenue gate (Part 3, #2). Build and persist every billing artifact regardless (consent + timestamp, per-day data-day log, minute log, interactive-call date/mode); the cost of capturing them is near zero and they cannot be reconstructed retrospectively.

**And flag a number that is probably wrong before anyone models revenue on it:** clinical §4.8.3 lists 98977 (16–30 data days) at ~$40 and 98985 (2–15 data days) at ~$51–52. A code requiring *less* data paying *more* is implausible on its face. Verify against the CY2026 fee schedule before it enters a deck.

---

### 1B. Hand-waves that must become exact numbers before code is written

| # | Item | Why it cannot stay vague |
|---|---|---|
| H1 | **`μ_pop`, `σ_g²`, `σ_i²` per metric × stratum** | Statistics §4.1.2 supplies only `B1`. `Ŷ = μ_pop + (X̄ − μ_pop)·B_n` is uncomputable without the other three, and the n=0 branch — the common case per completeness §1 — is *entirely* `μ_pop`. **There is no defensible population prior for wrist HRV or wrist skin temperature anywhere in the corpus.** Consequence nobody stated: those two metrics must be **personal-baseline-only and simply unavailable** below 7 valid pre-op days. That changes the available-weight arithmetic in Contradiction 3. |
| H2 | **Cross-scale variance floor for HRV** | Data §2.1.2 seeds `noise_sd["hrv_rmssd"] = 5.52` in **milliseconds**. Data §2.3.1 and statistics §4.1.4 both mandate `z` on **ln(RMSSD)**. `σ_eff = sqrt(σ_personal² + σ_device²)` cannot add ms to log-units. Needs an explicit delta-method conversion `σ_ln ≈ σ_raw / mean`, which requires storing the epoch's mean RMSSD. Nobody wrote it. |
| H3 | **`DEVICE_NOISE_SD` covers 2 of 6 metrics** | The table has HRV and RHR only — no skin temp, RR, steps, or SpO2. So §2.1.2's claim that it "replaces the arbitrary 0.06 relative SD floor" is true only for HRV. What floors the rest? |
| H4 | **Skin-temp floor: 0.05 vs 0.12 vs 0.25 °C** | Statistics §4.1.3 sets the device-resolution floor at 0.05 and §4.1.7 sets the operating floor at 0.25; the shipped code (`app/engine/baseline.py:14`) is 0.12. These are two different objects (sensor-pathology guard vs variance guard) and the design conflates them. Adjudication: 0.05 sensor-pathology, **0.25 variance**, both present, differently named. |
| H5 | **`ν₀ = 8` pseudo-observations** | Asserted, with "may itself be estimated from the cohort." It sets how hard every short baseline is shrunk. Pick it, log it, version it. |
| H6 | **`q = 0.02` Kalman** | "Fixed by fiat." BOCPD is refused *partly because* `q` is by fiat — the same objection applies to the filter that replaces the raw z. The Ljung-Box gate is the right mitigation; make its rejection rate a dashboard metric. |
| H7 | **Wear-evidence scoring 0–4, `VALID_DAY_MIN_SCORE = 3`** | Explicitly "reasoned analogues of Choi's parameters, not validated numbers" — and it gates the entire regulatory posture for a stack of general-wellness metrics. |
| H8 | **`expected_coverage(week) = 0.86 − 0.055·week`** | Derived from a shoulder-surgery cohort, applied to TKA/THA. Measure on the first 50 patients before hard-coding. |
| H9 | **Step-cliff `< 0.30 × 7-day median`** for dislocation | Entirely unvalidated, and it runs inside the step-suppression window (Contradiction 4). |
| H10 | **CRP procedure bands** | The design says "ship a procedure- and protocol-specific band" and then supplies no band — only two sources disagreeing by 50 mg/L at day 3. No band, no feature. |
| H11 | **`REBOUND_BAND_WIDENING = 1.5`, `BASE_BAND = 2.0`** | Product-defined and per-site configurable — fine, but the default must be chosen by a clinician and stamped, not by an engineer. |
| H12 | **PPV per rule per cohort** | Clinical §4.1.4 requires PPV printed on every card. Until an adjudicated cohort exists, the only honest value is the *published* PPV with its source cohort named and a `local_ppv: null`. Say that, or engineers will compute a fake one. |
| H13 | **Local-date confidence for Fitbit** | Fitbit returns local wall clock with **no IANA zone** — only a point-in-time offset. `local_date` is the join key for `daily_coverage`, POD, and **RTM billing day counts**. An off-by-one around travel or DST is a billing accuracy question, not a rounding question. Needs a `local_date_confidence` column and a documented tie-break rule. |
| H14 | **Navigator minutes per CONTACT** | See Contradiction 18. The number that decides whether the business works, and no section contains it. |

---

### 1C. Sequencing that is impossible as written

| # | Claimed sequence | Why it cannot happen | Correct order |
|---|---|---|---|
| S1 | Conformal calibration in month 2 | "Uneventful" is a **negative label** requiring 90-day follow-up and adjudication. The schema records no outcome of any kind, so the calibration pool is not small — it is unknowable. (The AI and statistics sections both say this; nothing in the plan reflects it.) | Outcomes schema in week 1; conformal is a year-2 item |
| S2 | Trajectory layer before aid capture | Steps suppressed by default forever without it (Contradiction 4) | Aid tap ships with the first check-in form |
| S3 | MUA projection before the PT channel | ESCALATE requires a clinician-measured ROM value | PT magic-link form precedes the alarm |
| S4 | Ingestion topology before Postgres | Per-patient FIFO under global concurrency 1 (Contradiction 23) | Postgres → topology |
| S5 | Elicited weights before the elicitation | The session is 8–12 surgeons' calendars | Founder schedules it in week 1 for a week-6 session |
| S6 | Junction connector "next quarter" | Fitbit sunsets inside the window (Contradiction 12) | Contract by day 10, connector by day 45 |
| S7 | ADT feed / Epic Stage 1 | Both require a signed customer's NPI and sponsorship | Post-first-customer |
| S8 | LifeSnaps replay before the detectors are pure functions of (history, as-of date) | Replay ≠ production unless that invariant holds, and it does not today (`compute_input_hash` folds `date.today()`) | Serving fix → as-of store → replay |
| S9 | Shadow-mode promotion inside 90 days | Requires ≥90 days and ≥30 completed episodes (Contradiction 25) | Baseline v1.0 frozen at enrollment |
| S10 | **The aggregate "ship now" backlog** | Data P0 ≈ 20 eng-days + AI ship-now ≈ 62 + clinical Phase 0 ≈ 30 + completeness Sprints 1–4 ≈ 40, before the unlisted Postgres migration, aid-capture UI, PT form and enrollment funnel. **~150+ eng-days of "immediate" work against ~120 eng-days of 90-day capacity at 2 engineers.** The plan is ~1.5× oversubscribed | See Part 2; things are cut |

---

## Part 2 — The ordered 90-day build plan

**Capacity assumption:** 2 backend engineers + 0.5 frontend, 13 weeks, ~4.5 productive days/week ≈ **125 engineer-days**. Plan below totals **119 eng-days**, leaving 6 days of slack, which is already optimistic. Clinical, regulatory and commercial work runs in parallel on the founder's and counsel's time and is **not** costed here.

**Blocking** means: work downstream of it is either wasted or unsafe if it starts first.

### Wave 0 — Days 1–15: foundation. Nothing else is safe first.

| ID | Item | Days | Blocking | Depends on |
|---|---|---|---|---|
| 0.1 | Merge the four documents into one spec with unique section IDs; delete the three `TIER_ORDER` corrections and the `2.2/24.7` walker figure | 1 | No | — |
| 0.2 | **Postgres/Aurora migration**: `practice_id` on every table, RLS policies, tenant-isolation integration test, concurrent-webhook load test, retire the S3-lock SQLite path | 12 | **Yes** | — |
| 0.3 | **Bitemporal `observations`**: append-only, `superseded_at`/`supersedes_id`/`revision`, partial unique index on `dedupe_key WHERE superseded_at IS NULL`, deterministic epoch resolution (C14) | 4 | **Yes** | 0.2 |
| 0.4 | **Outcomes schema**: `outcome_event`, `follow_up.last_known_contact`, `follow_up_complete`, `adjudicated_event`; stamp `engine_git_sha` + `config_version` + `prior_version` + `input_snapshot_hash` on every `RiskAssessment` | 3 | **Yes** (2-year lead time) | 0.2 |
| 0.5 | The rest of the schema, once, while the DB is open: `surgical_event`, `enrollment`, `assistive_device_periods`, `device_epochs`, `clinic_measurement`, `caregiver`, `practice_protocol`, `daily_coverage`, `symptom_events` | 5 | **Yes** | 0.2 |
| 0.6 | `dataload.py`: filter `deleted_at` + `superseded_at`, POD from `local_date`/`sleep_date` anchor | 1 | **Yes** | 0.3 |
| 0.7 | **Delete the post-op days 2–4 baseline fallback** (`app/engine/baseline.py:37`); `MIN_PREOP_DAYS = 7`; emit `INSUFFICIENT_BASELINE`; refuse numeric deviations below it | 2 | **Yes** — patient safety | 0.6 |
| 0.8 | Deny-by-default PHI egress flag + the five unit tests; PHI-free prompt serializer with a field allowlist | 2 | **Yes** for any LLM call | — |

**Subtotal 30 days.**

### Wave 1 — Days 16–30: make the engine honest and non-circular.

| ID | Item | Days | Blocking | Depends on |
|---|---|---|---|---|
| 1.1 | CI test hard-failing on any `app.seed → app.engine` import edge (AST walk) | 0.5 | No | — |
| 1.2 | **Break `curves.py` out of the scoring path** (C6): `expected_curve` artifact table seeded `hand_tuned_v0`; walking speed gets its own comparand; UI band labeled "illustrative, not a statistical interval" | 4 | **Yes** | 0.5 |
| 1.3 | `FUNCTIONAL_RATIO_SD` 0.10 → day-varying with floor 0.25 | 1 | No | 1.2 |
| 1.4 | Remove `GAIT_ASYMMETRY_HIGH` from `risk.py`; drop asymmetry + double-support from `ANALYZED_METRICS` and tier logic; keep as exploratory display | 0.5 | No | — |
| 1.5 | **Metric-family routing**: `HRV_SDNN` + `SKIN_TEMP_DELTA` into `ANALYZED_METRICS` and adverse sets, separate baselines per statistic, delta code path (`y_hat = 0`), family weights + renormalization + `MIN_METRICS_PRESENT` / `MIN_WEIGHT_PRESENT` gates | 4 | **Yes** | 0.6 |
| 1.6 | **Device × metric availability matrix** vs the 0.60 gate (C3); per-family gate or a `COMPOSITE_STRUCTURALLY_UNAVAILABLE` escalation | 1 | **Yes** | 1.5 |
| 1.7 | `log`-transform HRV and CRP before standardizing; skin-temp floors 0.05 sensor / 0.25 variance (H4) | 1 | No | 1.5 |
| 1.8 | `device_epochs` populated; **change-type → response matrix** (device / firmware / api_channel / source-device-rename), baseline reset on device change, no offset correction (C13) | 4 | **Yes** | 0.5 |
| 1.9 | EWMA daily-grid reindex; day-indexed CUSUM window; freeze CUSUM across non-wear; time-varying EWMA warm-up limits | 3 | **Yes** | 0.6 |

**Subtotal 19 days.**

### Wave 2 — Days 31–52: the actual signal, plus the aggregator deadline.

| ID | Item | Days | Blocking | Depends on |
|---|---|---|---|---|
| 2.1 | **Daily check-in**: 4-tap session (pain NRS, wound drainage ordinal, assistive device, exercises Y/N), app + SMS, grade-6 CI gate, TCPA consent/STOP/quiet hours, idempotency both directions | 9 | **Yes** | 0.5 |
| 2.2 | **Deterministic red-flag screen**, fail-closed: unmatched/non-English/unparseable → human queue + static reply; acknowledgment templates suppressed on any flag; LLM strictly monotonic | 4 | **Yes** — highest severe-harm path | 2.1 |
| 2.3 | **Wound pathway, precedence 0**: week-conditional ladder, de-escalation lane, published PPV/NNE per rule, `patient_line` as draft-only (C22) | 4 | No | 2.1 |
| 2.4 | Pain anchored non-monotonic curves + rebound window; `PAIN_ABOVE_EXPECTED`, `PAIN_REESCALATION` | 2 | No | 2.1 |
| 2.5 | **Junction connector + webhook signature verifiers + SQS + nightly 14-day trailing re-pull**; Fitbit→Google Health treated as same epoch, new `api_channel` | 8 | **Yes** — Fitbit sunset (C12) | 0.3, 1.8, founder contract |
| 2.6 | **Serving fix**: EventBridge → SQS fan-out → worker Lambdas; `/worklist` becomes a pure read; drop `date.today()` from `compute_input_hash`, add `max(revision)`; freshness/staleness banner; priority lane for red-flag ingests | 6 | **Yes** | 0.2 |
| 2.7 | **Episode state machine**: one open episode per patient, generalized `dedup_key` on `pathway` (C20), hysteresis, snooze with expiry, ack, append-only action log, notify only on open/escalation | 6 | **Yes** — largest multiplicity reduction | 2.3, 2.6 |
| 2.8 | Three-tier ladder WATCH / CONTACT / ESCALATE + once-daily digest; only ESCALATE pushes | 2 | No | 2.7 |

**Subtotal 41 days.**

### Wave 3 — Days 53–70: gates, coverage, and the regulatory artifact.

| ID | Item | Days | Blocking | Depends on |
|---|---|---|---|---|
| 3.1 | **Coverage/confidence rebuild**: `daily_coverage` materialized, wear proxy (sleep as *presence* not duration, H8/C8), per-statement-class minimum-data table, coverage-**residual** collapse detector, **text presence as a key metric**, drop SPO2 from the gate | 6 | **Yes** | 2.1, 0.5 |
| 3.2 | **Basis panel** (`engine/basis.py`) — purpose / inputs / algorithm / knowns-unknowns; rendered even on LLM fallback; **every tunable moved to a versioned config document** | 5 | **Yes** — FDA Criterion 4 | 1.5, 2.7 |
| 3.3 | LLM gates G1 schema + G2 numeric fidelity + G3 reason-code completeness; bundle manifest emitted by the engine; per-patient manifests on roster paths; cache key includes verifier/config/practice version. **G4 is batch-only, never in Lambda** (C28) | 4 | No | 3.2 |
| 3.4 | Banned-language expansion to a clinical lexicon + probabilistic frames; closed intent grammar with refusal-and-redirect; transcript injection stripping; Spanish mirror | 2 | **Yes** if any Spanish surface ships | 3.3 |
| 3.5 | **Clinician-authored action library keyed 1:1 to reason codes**, replacing LLM-originated suggested actions; validator rejects unmapped text | 3 | **Yes** — FDA | 3.2 |
| 3.6 | `coverage_manifest.yaml` + `not_watched` rendering in consent, console footer, and every worklist row | 2 | No | 3.2 |

**Subtotal 22 days.**

### Wave 4 — Days 71–90: the ROM/MUA channel, legibility, and the specificity number.

| ID | Item | Days | Blocking | Depends on |
|---|---|---|---|---|
| 4.1 | **PT magic-link `clinic_measurement` form** (no login, ≤60s) | 4 | **Yes** for 4.3 | 0.5 |
| 4.2 | Phone-inclinometer ROM capture with MDC95 change gates (flexion ≥9.0°, extension ≥3.1°); CONTACT-capable, ESCALATE requires a clinician value (C27) | 5 | No | 2.1 |
| 4.3 | **MUA flexion projection**, hand-rolled Theil–Sen (no scipy), fires POD 21–35 on projected <90° | 2 | No | 4.1, 4.2 |
| 4.4 | **30-second worklist contract**: tier + confidence + top-3 reason codes with raw values and units + published PPV + `data_as_of` + `not_watched` + episode days remaining; ordering driven **exclusively** by the deterministic tier | 4 | No | 2.7, 3.6 |
| 4.5 | **Seed regeneration**: Mitscherlich form, per-patient AR(1) φ~U(0.3,0.7), MCAR + MNAR gaps, walker period with ×0.64 step multiplier, one contralateral patient, one device-swap, one quitter | 4 | **Yes** for 4.6 | 1.1, 1.2 |
| 4.6 | **LifeSnaps + PMData replay**, brand-scoped (C17); ARL0 surface over φ ∈ {0,0.3,0.5,0.7}; **alert-budget CI test that fails the build**; bootstrap per participant | 5 | **Yes** — first real specificity number | 4.5, 2.7 |
| 4.7 | Red-team regression suite, v1 scope ~120 cases across the 7 failure modes + adversarial roster questions, in CI against recorded responses | 3 | No | 3.3, 3.4 |

**Subtotal 27 days. Grand total 119 eng-days.**

### Explicitly deferred past day 90 — and why

Parametric empirical Bayes and the moderated-variance rewrite (blocked on H1 — no population priors exist). Kalman innovations and the Ljung-Box gate (refinement to a corroborator). Conformal calibration (S1 — negative labels). Trajectory fits, Mitscherlich, ExpectileGAM, DTW lag (C5 — produces nothing before POD 38). Labs, UCUM, CRP bands (H10 — no band values). EHR Stage 1 and ADT (S7 — needs a customer). PROMs and the PRO-PM state machine beyond schema. Opioid and VTE modules. Wound photo capture. All retrieval, all MCP, all fine-tuning, the 510(k).

**Also not in the plan, and the founder should know it:** Aurora spend, A2P 10DLC brand registration lead time (1–3 weeks of carrier review — start it day 1, it is calendar-parallel and free), and the AWS BAA acceptance in Artifact.

---

## Part 3 — Decisions only the founder can make

These are business calls. Engineering can cost them and will implement whichever way they land, but choosing is not an engineering act.

**Gating the 90-day plan — needed in the first two weeks:**

1. **Aggregator: Junction, direct build, or neither — decided by day 10.** The Fitbit sunset is inside the window. Junction's $0.50/user figure is third-party and unpublished, and their docs state *no* default backfill window despite the corpus assuming 180 days. Both must be in writing before signing. Terra is disqualified (BAA only on custom Enterprise). This decision has a hard external deadline.

2. **Do we bill RTM in year one, and who writes the coding-and-coverage opinion?** The §201(h) bifurcation — data-capture front end as a possibly-exempt Class I device, analytics back end as non-device CDS — is a counsel question that gates all revenue. Billing 9897x while telling FDA we are not a device is False Claims Act territory. Until the memo exists we build the billing evidence and bill nothing. **How many weeks of runway are you willing to spend on that memo?**

3. **What are we actually selling?** PT substitution + PRO-PM compliance + documented review, or "we detect complications earlier." The evidence permits only the first — the definitive readmission RCT (n=4,736) is null, and mymobility's app arm had *worse* 90-day KOOS JR. This decides the marketing SOP, the intended-use statement, the FDA position, and half the roadmap.

4. **Pre-operative enrollment lead time.** Ask three partner practices for the distribution of scheduling-to-surgery intervals. If the median is under 7 days, the personal-baseline architecture is not viable and the product ships in borrowed-prior mode by default — which, given H1, means HRV and skin temperature are unavailable at enrollment for most patients. **This single number decides whether the statistical spine of the product works.** It requires a phone call, not an engineer.

5. **Launch procedure: TKA only, or more?** The corpus has defensible curves for TKA, THA, ACL and rotator cuff, and none for ankle, meniscus, bilateral or revision. Every additional procedure at launch is a fabricated curve or a `TRAJECTORY_UNAVAILABLE` state in the demo.

**Economic model — needed before the first customer:**

6. **The navigator budget, in minutes.** Set the maximum CONTACT items per navigator per day. The mandatory monthly interactive call alone is ~1.0 FTE at 500 patients, before any alert review. This number, not any statistical parameter, determines whether the unit economics close — and it is the constraint we will tune the thresholds against.

7. **Schedule the surgeon weight-elicitation session** (SHELF-roulette or pairwise AHP, 8–12 surgeons, ≥2 per response tier for the net-benefit thresholds). The composite weight vector currently has no author, and no engineering process can produce one.

8. **Devices: BYOD or supplied?** $250–400 CapEx per patient plus reverse logistics against ~$400 of billing, versus excluding 35–40% of a mean-age-66 cohort and biasing the analytics population young and affluent. Neither branch is costed anywhere in the corpus.

9. **The 20% Part B coinsurance (~$8–11/month).** Who discloses it, when, and who absorbs the complaint call to the surgeon's front desk? This is the most predictable churn mechanism in the product and it appears once, as a compliance footnote.

10. **The 365-day TKA surveillance tail.** ~42% of primary TKA PJIs declare between day 91 and 365 — a real and differentiating claim. But RTM revenue stops around month 3 and TEAM stops at day 30. Committing to the tail is a cost decision funded by nothing except the PRO-PM capture you must do anyway.

11. **Do you have a PT partner?** Completeness §2 is right that the PT is the missing user, the missing data stream, and a distribution channel — and that the highest-dollar alarm (MUA) cannot escalate without them. Whether a PT group will fill a magic-link form weekly is a relationship question.

**Risk posture — needed before the first patient:**

12. **Do patient-facing messages ever auto-send?** My recommendation is never, except the static 911/practice safety tier. Auto-send is the FDA bright line, the AB 3030 safe harbor, and the liability boundary all at once. If you want auto-send for engagement reasons, say so now and we build the review queue differently.

13. **Legal spend and counsel selection.** The FDA regulatory-rationale memo written statute-first, verification of the January 2026 CDS guidance text (one reviewer got a 404 on the primary URL), the 50-state AI-disclosure matrix, TCPA consent architecture, and the RTM coding opinion. This is a real budget line with a real calendar.

14. **LLM vendor:** Groq paid + BAA, Bedrock, or the de-identified serializer alone. My engineering position (C29) is that the serializer removes the blocker; the BAA is cheap optionality. But the spend and the vendor relationship are yours.

15. **Shadow-mode duration and pre-registered promotion criteria.** Statistics and AI both demand ≥90 days, ≥30 episodes, ≥5 high-tier events before promoting any engine version. At 10–50 concurrent patients that is 3–6 months, and if the census never reaches 5 high-tier events you must decide *in advance* whether to lower the gate or extend the pilot. Deciding after seeing the data is not a decision, it is a rationalization. **Pre-register it in writing before the first patient.**

16. **Do you ever intend to sell prediction?** If probabilities, near-term deterioration, or streaming-signal analytics become the product, that is a 510(k) at roughly $250k and 12 months (product code QNL, predicate AgileMD eCARTv5 K233253), and it should be planned with a PCCP from the start. If not, the non-device line holds and the ceiling is ordinal tiers with typed reason codes, forever. **Every architectural decision in this plan assumes the second answer.**

17. **$25–60k for PearlDiver base rates.** Optional. A deviation threshold without a prevalence is meaningless, and AJRR/AOANJRR annual-report rates are free and directionally sufficient. Spend it only if a customer conversation requires their own population's numbers.

---

## The three things I would fight about

If I get overruled on everything else, these three:

- **Postgres before the first patient.** A write collision that silently discards a febrile check-in under the S3-lock SQLite path is a safety failure with no error and no trace. Twelve days is cheap.
- **The post-op days 2–4 baseline fallback is deleted in Wave 0.** In its current form the engine reads normalization as deterioration and sustained elevation as on-track — it reassures about the exact patient it exists to catch. Two days of work.
- **The outcomes and follow-up schema ships in week one even though it does nothing for a year.** Every calibration, every threshold, every claim, and every retrospective analysis is downstream of a negative label that cannot be reconstructed after the fact. Three days now, or two years lost.