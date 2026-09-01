# Conversational AI check-in for post-op orthopedic RTM — evidence, safety architecture, SMS implementation, and RTM billing design

## Summary

The evidence supports a structured, scripted SMS chatbot for post-op orthopedic recovery — and specifically does NOT support a free-form LLM conversation. The best ortho-specific RCT (Campbell et al., JBJS 2019, n=159 TJA patients) showed a scripted SMS bot increased daily exercise (+8.6 min/day), got patients off opioids 10 days sooner, cut calls to the surgeon's office from 2.6 to 0.6, and improved 3-week knee flexion by ~7 degrees. But the definitive readmission evidence is negative: Bressman's 2024 JAMA Network Open RCT (n=4,736) of 30-day tapered post-discharge texting found zero effect on acute-care revisits (RR 1.02), despite 79.5% engagement — reversing his own 2022 cohort study (OR 0.45 for readmission). So sell engagement, triage efficiency, PRO capture, and RTM revenue — never readmission reduction. Design-wise: 3-4 tap-to-answer questions per day gated by postoperative-day stage, tapering cadence (daily weeks 1-2, then 3x/week, then weekly), sixth-grade reading level (AMA/NIH standard), and validated instruments (KOOS JR/HOOS JR) delivered intact via web link at fixed timepoints — conversational decomposition of a validated instrument is a "substantial modification" under the ISPOR ePRO framework (Coons 2009) requiring full psychometric revalidation, so don't do it. Safety must be a deterministic keyword/branch red-flag screen that runs before and independent of any LLM, with an instant "call 911" auto-reply and an explicit, repeated "not monitored in real time" disclosure. Infrastructure: AWS End User Messaging (HIPAA-eligible, already inside your AWS BAA) over Twilio (BAA requires Security/Enterprise edition), A2P 10DLC low-volume standard registration, minimal PHI in message bodies, and conversation state as a versioned DB table with idempotency on provider message IDs. RTM billing works (98975/98977/98980/98981, ~$113/patient/month at 2025 rates) but has two traps: the 98980/98981 "interactive communication" must be real-time audio/video — an SMS thread does not qualify — and 98977 requires the data to come from an FDA-definition medical device, which a bare SMS survey likely is not.

## Findings

### Scripted SMS chatbot after TJA improved recovery behaviors in an RCT
*[strong]*

Campbell KJ, Louie PK, Bohl DD et al., J Bone Joint Surg Am 2019;101(2):145-151 (PMID 30653044), RCT n=159 TKA/THA: SMS-bot arm exercised 8.6 min/day more (46.4 vs 37.7 min), stopped narcotics 10 days sooner (22.5 vs 32.4 days), made 2.0 fewer calls to the surgeon's office (0.6 vs 2.6), had better mood (VAS 7.5 vs 6.5) and greater 3-week knee flexion (101.2 vs 93.8 degrees). This is the closest published analog to what MedPull should build: fully scripted, stage-aware texting — no generative model.

> https://pubmed.ncbi.nlm.nih.gov/30653044/

### Definitive RCT: automated post-discharge texting does NOT reduce readmissions
*[strong]*

Bressman et al., JAMA Netw Open 2024 (PMID 38564221), RCT n=4,736: 30-day tapering automated texting from primary care produced identical 30-day acute-care revisits (23.9% vs 23.4%, RR 1.02, 95% CI 0.92-1.13) — despite 79.5% of patients answering at least one message and needs identified in 41.9%. This reversed the same group's 2022 propensity-matched cohort (PMID 36287564, aOR 0.45 for readmission, 0.59 for any acute care). Do not put readmission reduction in any MedPull claim, pitch, or consent language; the honest value proposition is engagement, early problem identification, and staff-call deflection.

> https://pubmed.ncbi.nlm.nih.gov/38564221/ ; https://pubmed.ncbi.nlm.nih.gov/36287564/

### Twice-daily automated messaging with psychological content improved function in delayed TJA patients
*[moderate]*

Anthony CA et al., J Arthroplasty 2022;37(3):431-437 (PMID 34906660), RCT n=90: 14 days of twice-daily automated ACT-based messages — 38% achieved clinically important physical-health improvement vs 17.5% control; 24% vs 2.5% on joint-specific scores; functional decline 14% vs 41.7%. Supports message content beyond symptom capture (encouragement, coping) delivered by template.

> https://pubmed.ncbi.nlm.nih.gov/34906660/

### Ortho-specific chatbot-for-physio-adherence evidence is still thin
*[weak]*

Blasco et al., BMC Musculoskelet Disord 2023 (PMID 37322506) is a protocol (NCT05363137, n=70, chatbot to promote home physiotherapy adherence after TKR, excludes patients >75) — results not yet the basis for claims. The 2025-2026 chatbot-in-arthroplasty literature is mostly ChatGPT-answers-patient-questions studies, not longitudinal check-in trials. MedPull would be near the front of the evidence, which argues for conservative, auditable design.

> https://pubmed.ncbi.nlm.nih.gov/37322506/

### Expected compliance ceiling ~79%, and incentives are the only design lever that reliably moves it
*[strong]*

Wrzus & Neubauer 2023 meta-analysis of ambulatory assessment (PMID 35016567; 477 articles, N>677,000): average compliance 79% (typical design: 6 prompts/day for 7 days); total number of assessments showed no significant relationship with compliance or dropout, and only financial incentives significantly raised compliance. Plan for 20-30% non-response from day one; Bressman's RCT (79.5% ever-engaged over 30 days with a tapering schedule) matches. Design the RTM data-day economics (16/30 days) assuming ~70-80% response, i.e., you need ~21+ scheduled days in month one to reliably clear 16 data days.

> https://pubmed.ncbi.nlm.nih.gov/35016567/

### Reading level standard: sixth grade or below (AMA and NIH)
*[strong]*

AMA and NIH recommend patient education materials at no greater than sixth-grade reading level (Eltorai et al., PMID 27218045; consistently cited across orthopedic readability studies, e.g. Roberts et al. PMID 27605695 found only 3.9% of materials met it). Enforce mechanically: run Flesch-Kincaid grade on every message-template string in CI and fail the build above grade 6. Your existing deterministic-renderer discipline extends naturally to this.

> https://pubmed.ncbi.nlm.nih.gov/27218045/

### Conversationally rendering a validated PRO instrument invalidates its psychometrics
*[strong]*

ISPOR ePRO Good Research Practices Task Force (Coons SJ et al., Value in Health 2009;12(4):419-429, PMID 19900250) defines three modification tiers: minor (cognitive debriefing/usability), moderate (equivalence testing), substantial (full psychometric re-validation). Splitting KOOS JR/HOOS JR/PROMIS items across days, rewording them chat-style, or letting an LLM paraphrase them is a substantial modification — the resulting scores are not the instrument's scores and cannot be reported as such. Deliver validated instruments intact (single web-link session, original wording, original response options) at fixed timepoints; keep the daily chat items as your own non-claimed symptom battery feeding your deterministic engine.

> https://pubmed.ncbi.nlm.nih.gov/19900250/

### RTM economics: ~$113/patient/month at 2025 Medicare rates, gated by the 16-day rule
*[strong]*

2025 national non-facility rates: 98975 setup/education $19.73 (once per episode); 98977 musculoskeletal device supply $43.02 per 30 days requiring >=16 days of data; 98980 first 20 min of treatment management/month $50.14; 98981 each additional 20 min $39.14. Typical month for an engaged patient: 98977 + 98980 = ~$93; month one adds 98975. Documentation payers expect: patient consent, ordering provider, device/data-day log showing the 16 days, itemized time log totaling 20 min of management, and the date/mode of the interactive communication.

> https://www.tenovi.com/rtm-cpt-codes/

### An SMS thread does NOT satisfy the 98980/98981 'interactive communication' requirement
*[moderate]*

CPT 98980/98981 require at least one interactive communication with the patient/caregiver during the calendar month; CMS has defined interactive communication (in RPM 99457 rulemaking, applied to RTM) as at minimum a real-time synchronous two-way audio interaction capable of being enhanced with video (CY2021 PFS final rule, 85 FR 84472; reiterated in subsequent PFS rules). Asynchronous texting does not qualify. Design consequence: the chatbot earns the 16 data days and surfaces the worklist, but a human must place one real-time phone/video call per billing month — build a 'monthly interactive communication due' task into the worklist with date/mode capture. (Could not fetch the rule text directly this session — verify the FR citation before compliance sign-off.)

> 85 FR 84472 (CY2021 Medicare PFS final rule); CPT 2025 codebook descriptors for 98980/98981

### RTM's 'medical device' requirement is the biggest legal gray zone for an SMS-only check-in
*[moderate]*

RTM codes (98975-98977) are valued as supply of a device: CMS requires RTM data be collected by a product meeting the FDA definition of a medical device (FDCA Sec. 201(h)), though patient self-reported data entered into that device is allowed (unlike RPM's physiologic-data requirement). Software-as-a-Medical-Device can qualify, and RTM vendors position their apps that way, but a bare Twilio/AWS SMS survey with no listed device function is hard to defend as a 201(h) device. Mitigation: register/classify the MedPull patient app (or a specific software module) as the RTM 'device' pathway and route SMS answers into it; get healthcare-regulatory counsel to bless the position before billing 98977.

> 86 FR 65248 (CY2022 PFS final rule establishing RTM); FDCA Sec. 201(h)

### AWS End User Messaging is HIPAA-eligible and the cheapest compliant path given your stack
*[strong]*

AWS's official HIPAA Eligible Services Reference lists 'Amazon Pinpoint and End User Messaging' as eligible excluding Voice and WhatsApp; Lambda, DynamoDB, SNS, and Connect are also eligible. Since MedPull already runs on Lambda/CloudFront under an AWS account (BAA via AWS Artifact is self-service and free), SMS via AWS End User Messaging keeps one vendor and zero incremental BAA cost. Twilio signs a BAA only on Security Edition or Enterprise Edition plans (negotiated, sales-gated, typically five figures/year) — a bad fit at pilot scale.

> https://aws.amazon.com/compliance/hipaa-eligible-services-reference/ ; https://www.twilio.com/en-us/hipaa

### A2P 10DLC registration is mandatory and rate-limits you by brand tier
*[strong]*

US 10-digit-long-code application messaging requires brand registration (who you are) plus campaign registration (use case, opt-in/opt-out flow, sample messages). Low-Volume Standard brands get roughly 2,000 msgs/day to T-Mobile (~6,000/day across carriers); Standard brands scale with Trust Score. Campaign review takes days to weeks — start registration before writing code. Healthcare messaging is an accepted use case, but campaigns must document opt-in, honor STOP/HELP keywords, and avoid forbidden categories. One-time brand fee (~$4-44), per-campaign monthly fee (~$1.50-10), plus per-message carrier surcharges on top of base SMS price (AWS EUM US outbound SMS ~$0.00581 + carrier fees).

> https://www.twilio.com/docs/messaging/compliance/a2p-10dlc

### TCPA/HIPAA framework for the messages themselves
*[moderate]*

Providing a phone number to a healthcare provider constitutes prior express consent for non-telemarketing healthcare messages (FCC 2012 SoundBite ruling; 2015 TCPA Omnibus Order, 30 FCC Rcd 7961), and 47 CFR 64.1200(a)(9) exempts free-to-end-user HIPAA healthcare messages under conditions including frequency caps (commonly cited as max 1/day and 3/week for the exemption pathway) and immediate opt-out honoring. Safer posture: obtain documented written consent at enrollment (which RTM requires anyway), send within 8am-9pm local quiet hours, honor STOP instantly. PHI in SMS: HIPAA permits unencrypted SMS if the patient is warned of the risk and agrees (OCR guidance on patient communication preferences) — but keep bodies content-minimal anyway (first name, question text; never diagnosis, procedure, or med names). eCFR text could not be fetched this session — verify the (a)(9) frequency caps verbatim before finalizing cadence defaults.

> 47 CFR 64.1200(a)(9); FCC 15-72 (2015 TCPA Omnibus Declaratory Ruling)

### Post-op orthopedic red flags requiring deterministic escalation (standard of care, not model judgment)
*[strong]*

The battery every arthroplasty/ortho discharge protocol screens for: (1) chest pain, shortness of breath, coughing blood — pulmonary embolism, call 911; (2) new unilateral calf pain, swelling, warmth — DVT, same-day urgent evaluation; (3) fever >=101.5F plus increasing wound redness, drainage, or odor — surgical site infection; (4) sudden inability to bear weight, new deformity, or audible pop — periprosthetic fracture/dislocation; (5) pain uncontrolled despite prescribed medication; (6) suspected medication reaction (rash, vomiting, confusion, black stools on anticoagulants); (7) any self-harm/suicidal ideation — respond with 988 Suicide & Crisis Lifeline and escalate. These come from AAOS/AAHKS discharge standards and VTE prophylaxis guidance; they must be implemented as keyword/regex plus structured-branch triggers evaluated before any LLM sees the text, with the LLM result never able to downgrade a deterministic hit.

> AAOS OrthoInfo discharge/VTE guidance; AAHKS patient education standards

### Tapering cadence is the field's convergent answer to question fatigue
*[moderate]*

Both the Penn program (daily then tapering over 30 days) and EMA best practice converge on front-loaded frequency: daily during POD 1-14 when complications cluster (most SSI, DVT, and pain crises present in weeks 1-3), stepping to 3x/week through POD 42, weekly to POD 90. Wrzus 2023 shows total assessment burden doesn't drive dropout, but clinically the information value per question collapses after week 6 — taper to match. Single reminder 3-4 hours after an unanswered prompt; mid-morning send (9-10am local) sits inside TCPA quiet hours and before afternoon PT sessions.

> https://pubmed.ncbi.nlm.nih.gov/38564221/ ; https://pubmed.ncbi.nlm.nih.gov/35016567/

### Machine-translating clinical questions on the fly is a documented harm vector; use fixed human-verified scripts
*[moderate]*

Since the question battery is finite and scripted, translate it once with qualified human review (Spanish first) rather than runtime MT — mistranslation of symptom questions (e.g., 'drainage', 'numbness') changes clinical meaning, and ACA Section 1557 obligates meaningful language access for covered entities. Inbound free-text in other languages may be machine-translated for staff display only, flagged as machine-translated, and must still pass the (per-language) deterministic red-flag lexicon. This aligns with the project's existing AWS Translate preference but restricts it to inbound triage display, never outbound clinical questions.

> 45 CFR Part 92 (Section 1557); ISPOR translation good practice (Wild et al. 2005)


## Implications for backend

- Conversation state lives in the existing SQLAlchemy database as a conversation_state table (episode_id, protocol_id, current_node, awaiting_reply_to, expires_at, version int for optimistic locking) — works on SQLite today and Postgres later; do not add DynamoDB just for this. Inbound idempotency = unique constraint on the provider message ID; outbound idempotency = deterministic send-key (patient_id, protocol_node, local_date) checked before publish, since Lambda retries and webhook redeliveries are guaranteed to happen.
- The red-flag screen belongs in backend/app/engine as a pure function returning the same typed reason codes the risk-tier logic already emits (e.g., RED_FLAG_PE_SYMPTOMS, RED_FLAG_DVT_SYMPTOMS, RED_FLAG_SSI_SYMPTOMS, RED_FLAG_SI). It runs on every inbound message before any LLM call, its output is never modifiable by LLM output, and it gets golden-tier pinned tests like the existing engine (matching the project's established pattern).
- Daily check-in answers become a first-class signal source for the existing deterministic analytics: pain 0-10 feeds EWMA/CUSUM deviation, response/non-response feeds the adherence metric and doubles as the RTM 16-day data-day counter, and 3+ consecutive missed days should itself raise a worklist item (non-response after early engagement is a known deterioration signal).
- Scheduling needs a timezone-aware EventBridge-driven send Lambda honoring 8am-9pm TCPA quiet hours per patient locale, with a single reminder 3-4h after non-response — the current request/response Lambda shape gains its first cron-driven outbound path.
- The existing LLM guardrail stack (JSON contract validation, banned-diagnostic-language filter, mandatory guardrail sentence, deterministic fallback, input-hash caching) is reused unchanged for the only two LLM jobs in the check-in: free-text intent classification into typed codes and template acknowledgment selection. Groq llama-3.3-70b stays; the deterministic renderer is the fallback for every acknowledgment.
- New compliance artifacts the backend must persist per patient: SMS consent + risk acknowledgment timestamp, RTM consent, ordering provider, STOP/opt-out state (must halt sends instantly and survive re-enrollment), per-month data-day and management-minutes logs, and the date/mode of the monthly interactive phone call — these are billing evidence, not just app state.

## Recommendation
**Build a deterministic, stage-aware scripted SMS check-in (a branching state machine, exactly like Campbell 2019's bot) delivered via AWS End User Messaging under your existing AWS BAA, with a keyword/branch red-flag screen that runs before and independent of any LLM. Use the LLM only for (a) classifying free-text replies into your existing typed reason codes after the deterministic screen has run, and (b) selecting/lightly-rendering template acknowledgments through your existing guardrail pipeline. Deliver KOOS JR/HOOS JR intact via web link at fixed timepoints, never conversationally. Bill RTM with a human monthly phone call for 98980 and defer 98977 until counsel blesses a device position.**

Every published win in this space (Campbell JBJS 2019, Anthony 2022, Penn's program) used fully scripted branching messages — none used generative AI, and the one large RCT shows engagement (79.5%) but no readmission effect, so the ROI is engagement, call deflection, PRO capture, and RTM revenue, all of which a scripted flow captures at a fraction of the risk. A free-form LLM conversation adds no evidenced benefit, creates an unbounded safety surface (hallucinated reassurance is the failure mode that kills the product), invalidates PRO psychometrics if it touches instruments, and doesn't even help billing since CMS requires real-time audio for the management codes anyway. The deterministic-first architecture also matches MedPull's existing engineering DNA: the analytics engine already produces every number deterministically, and the red-flag screen is the same pattern — typed reason codes from pure functions, LLM strictly for rendering.

**Do NOT:**
- Do not build free-form LLM conversation for check-ins — no trial evidence supports it, and a single hallucinated 'that sounds normal' to a PE symptom is an existential liability; the LLM must never be able to suppress, rephrase, or gate a red-flag escalation.
- Do not decompose or paraphrase KOOS JR/HOOS JR/PROMIS into chat questions — under ISPOR (Coons 2009) that is a substantial modification requiring full revalidation; the scores would be unpublishable and clinically meaningless.
- Do not claim readmission reduction anywhere (sales, consent, UI) — the definitive RCT (n=4,736, JAMA Netw Open 2024) is null.
- Do not bill 98980/98981 on the basis of the SMS thread — CMS requires real-time synchronous audio at minimum; and do not bill 98977 until you have a defensible FDA-device position for the software.
- Do not put diagnosis, procedure, medication names, or clinical details in SMS bodies; do not machine-translate outbound clinical questions at runtime.
- Do not use Twilio at pilot scale — its BAA is gated behind Security/Enterprise Edition; AWS End User Messaging is HIPAA-eligible inside your existing account.
- Do not imply real-time monitoring: every red-flag auto-reply must instruct 911/urgent action immediately and never say 'we will get back to you' for emergency symptoms; the 'not monitored in real time, if this is an emergency call 911' disclosure goes in the consent, the welcome message, and a recurring footer.

**Sequencing:**
- Week 0 (calendar-parallel): register A2P 10DLC brand + healthcare campaign via AWS End User Messaging; execute/confirm AWS BAA via Artifact; draft enrollment consent covering SMS risk acknowledgment, RTM consent, and not-monitored-in-real-time disclosure. (~2-3 days work, 1-3 weeks carrier review.)
- Weeks 1-3: build the check-in engine in backend/app/engine — protocol tables keyed by postoperative day (POD 1-14 daily: pain 0-10, exercises done Y/N, med question, one rotating item; POD 15-42 3x/week; POD 43-90 weekly), each question tap-to-answer (digits/Y-N), whole exchange under 60 seconds; conversation_state table (episode_id, protocol_node, awaiting_reply, expires_at, version) with optimistic locking, EventBridge-scheduled send Lambda with idempotency key (patient+node+date), inbound webhook with unique constraint on provider message-id for dedupe; Flesch-Kincaid <=6 CI gate on all message strings. (~2-3 wks)
- Weeks 2-4 (overlapping): deterministic red-flag layer — per-category keyword/regex lexicons + structured-branch triggers (chest pain/SOB, calf pain/swelling, fever+wound signs, can't bear weight, uncontrolled pain, med reaction, self-harm/988), evaluated on every inbound message before anything else; hit => instant templated safety reply with 911/nurse instruction + escalation row in the existing worklist with typed reason code + practice notification; nightly test suite of adversarial phrasings. (~1-2 wks)
- Weeks 4-5: RTM documentation surface — data-day counter toward 16/30, time log for management minutes, 'monthly interactive phone call due' worklist task with date/mode capture; engage healthcare-regulatory counsel on the 98977 device question. (~1 wk build)
- Weeks 5-7: LLM intent classification of free-text replies into existing typed reason codes (runs only after red-flag screen; validated against JSON contract; fallback = route raw text to staff), feeding pain/function answers into the existing EWMA/CUSUM deviation engine as a new signal source. (~1-2 wks)
- Weeks 6-8: fixed-timepoint validated PROs — KOOS JR/HOOS JR via web link at pre-op, 6wk, 3mo, 6mo, 1yr, stored alongside daily battery but scored per instrument manual. (~1 wk)
- Weeks 8-10: Spanish scripts via qualified human translation with clinician review; per-language red-flag lexicon; inbound MT for staff display only. (~1-2 wks)

## Open questions

- Can the MedPull app/software module defensibly qualify as an FDA 201(h) medical device so 98977 (device supply, $43.02/30 days) is billable, or does the pilot bill only 98975+98980? Needs healthcare-regulatory counsel; this is the single biggest revenue-architecture fork.
- Exact current text of 47 CFR 64.1200(a)(9) frequency caps for the free-to-end-user healthcare exemption (eCFR fetch was blocked this session) — verify before hard-coding cadence defaults, though documented written consent at enrollment largely moots the exemption pathway.
- CY2026 Physician Fee Schedule: CMS proposed shorter-duration remote monitoring codes (sub-16-day data periods) in the July 2025 proposed rule — confirm what was finalized for 2026, since it could relax the 16-day gate that currently forces the front-loaded cadence.
- What fraction of the target practices' payer mix reimburses RTM at all (commercial adoption is uneven), and will practices actually staff the monthly real-time phone call and the escalation queue during business hours — the design assumes a named human owner for both.
- Expected patient volume vs A2P 10DLC tier: Low-Volume Standard (~6,000 msgs/day) covers roughly 1,500-2,000 active patients at the tapered cadence; beyond that, Standard brand vetting and Trust Score work is needed.
- Whether the Blasco NCT05363137 TKR-chatbot trial has published results by launch (protocol was 2023) — it would be the first direct RCT evidence for chatbot-driven physio adherence in this exact population and worth citing if positive.