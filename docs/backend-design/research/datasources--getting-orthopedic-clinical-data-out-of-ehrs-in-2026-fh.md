# Getting orthopedic clinical data out of EHRs in 2026: FHIR/US Core/USCDI status, SMART v2 and Bulk Data, vendor developer programs (Epic, Oracle Health, athenahealth, ModMed), regulatory levers (HTI, CMS-0057-F, TEFCA, information blocking), and aggregator/patient-mediated alternatives

## Summary

The US EHR interoperability floor in 2026 is FHIR R4 (4.0.1) + US Core (current STU 9.0.0, May 2026, still R4-based; R5 skipped, next base will be R6) + USCDI v3, which became the mandatory certified-EHR baseline on Jan 1, 2026 under HTI-1; nothing beyond USCDI v3 can be assumed from every certified system before ~2028. Read access to the ortho-relevant profiles we need (Patient, Condition, Procedure, Observation, MedicationRequest, Encounter, DiagnosticReport, DocumentReference, CarePlan, Goal, QuestionnaireResponse, ServiceRequest, AllergyIntolerance) is free at Epic via open.epic and at Oracle Health via Code Console, but every single health-system connection requires that customer's own approval and IT work — that governance step, not the API, is the pacing item. Write-back to Epic is narrowly possible (flowsheet observations, document submission, questionnaire responses) but there are no order/CarePlan writes through open APIs. Bulk $export is real but slow at Epic (~1,555–2,500 resources/min, no _since parameter), so per-patient incremental SMART Backend Services reads are the right ingestion pattern for an RTM cohort. The strongest near-term regulatory levers are TEFCA Individual Access Services (patient-mediated FHIR pull of USCDI v1/v3 from all Epic Nexus participants, IAL2 identity proofing required) and CMS-mandated hospital ADT e-notifications for readmission detection; CMS-0057-F's Provider Access API (Jan 1, 2027) becomes a payer-side channel later. Aggregators (Particle ~$60k/yr+, Health Gorilla custom, Metriport open-source/custom, Flexpa $20k/yr claims-focused) buy network reach but carry treatment-purpose eligibility risk for a monitoring vendor, as the Epic–Particle dispute showed. Recommended staging for a startup: patient-mediated + per-customer Epic/ModMed connections first, aggregator only at volume.

## Findings

### FHIR version reality: R4 is the only version that matters through ~2028; US Core is now STU 9.0.0
*[strong]*

US Core Implementation Guide v9.0.0 (STU 9) was published May 31, 2026, and is still based on FHIR R4 (4.0.1). The US Realm Steering Committee decided in January 2024 that US Core will skip R4B/R5 entirely and move next to FHIR R6. All 13 profiles we need exist in US Core: Patient; Condition (two profiles: Encounter Diagnosis, and Problems and Health Concerns); Procedure; Observation (Clinical Result, Laboratory Result, Vital Signs incl. pediatric variants, Smoking Status, Screening Assessment); MedicationRequest; Encounter; DiagnosticReport (Laboratory, and Report and Note Exchange); DocumentReference (General + ADI); CarePlan; Goal; QuestionnaireResponse; ServiceRequest; AllergyIntolerance. Certified-EHR (g)(10) servers are only required to support the US Core version referenced in regulation (3.1.1/6.1.0 era), so code defensively against older US Core versions in production servers.

> HL7 US Core IG v9.0.0, 2026, https://hl7.org/fhir/us/core/

### USCDI v3 is the mandatory certified-EHR baseline as of Jan 1, 2026; v4/v5 are NOT yet required
*[moderate]*

HTI-1 final rule (effective March 11, 2024) adopted USCDI v3 as the ONC/ASTP Certification Program baseline effective January 1, 2026. USCDI v4 was proposed as mandatory by Jan 1, 2028 in the HTI-2 proposed rule (Aug 2024), but the December 2024 HTI-2 final rule finalized mainly TEFCA-related provisions, leaving the v4 API mandate not yet in force; USCDI v6 was published July 2025 and draft v7 in January 2026 as voluntary standards. Practical consequence: elements added in v4/v5 (e.g., more granular functional status, advance directives) cannot be assumed from every certified EHR before ~2028. HTI-1 also revised information-blocking exceptions and added the TEFCA 'manner' exception.

> HealthIT.gov HTI certification program page, 2024-2026, https://www.healthit.gov/topic/laws-regulation-and-policy/health-data-technology-and-interoperability-certification-program

### SMART App Launch v2.2.0: granular v2 scopes and Backend Services are the auth substrate for everything
*[strong]*

Current spec is SMART App Launch v2.2.0 (HL7). v2 granular scopes use resource.rs syntax with search-parameter qualifiers, e.g. patient/Observation.rs?category=http://terminology.hl7.org/CodeSystem/observation-category|vital-signs; servers advertise 'permission-v2' capability. Certified (g)(10) servers were required to support SMART v2 scopes by end of 2024 under HTI-1. SMART Backend Services (system-level, no user) uses JWT client-credentials with asymmetric keys (RS256/RS384/RS512/ES256/ES384 accepted by Epic; spec recommends RS384/ES384), a registered JWKS URL, and system/ scopes (e.g. system/Observation.rs); it works for both Bulk Data and ordinary synchronous FHIR reads. User-launched (EHR launch or standalone patient launch via MyChart credentials) is the alternative when the health system won't pre-authorize a system client.

> HL7 SMART App Launch v2.2.0, 2024, https://hl7.org/fhir/smart-app-launch/ and https://hl7.org/fhir/smart-app-launch/backend-services.html

### FHIR Bulk Data $export works but is slow at Epic: 1,555–2,500 resources/min, no _since support
*[strong]*

A peer-reviewed multi-site benchmark found three Epic sites exported 1–12 million resources at 1,555–2,500 resources/min; Oracle Cerner sites did 5–16 million resources at >8,000 resources/min; a custom HIE API hit 12,000 resources/min over 141M resources. Epic has implemented _typeFilter but NOT the _since incremental parameter, so full-history exports are impractical — recommended workaround is date-windowed _typeFilter ranges slid forward, or the open-source SMART 'Fetch' crawler doing per-patient reads instead of $export. For an RTM cohort of hundreds of patients, per-patient synchronous reads via Backend Services beat Bulk Data outright.

> PMC benchmark study + smart-on-fhir/cumulus Epic tips, 2023-2024, https://pmc.ncbi.nlm.nih.gov/articles/PMC11031206/ and https://github.com/smart-on-fhir/cumulus/discussions/5

### Epic developer economics: free USCDI read APIs, Vendor Services from $1,900/yr, per-customer approval is the real gate, App Market replaced by Showroom/Connection Hub
*[strong]*

open.epic registration, sandbox, and the published USCDI-on-FHIR read APIs are free with no Epic licensing fee. Optional Vendor Services subscription starts at $1,900/year (3-month refundable trial) and buys support, additional technologies, and testing tools; the old App Orchard/App Market revenue-share model was dismantled — Connection Hub is a free directory requiring at least one live Epic customer connection, and Showroom lists vetted 'Toolbox' partners. Critically, every production connection requires the individual health system's approval and build work (security review, InterConnect config); Epic corporate does not gate it — customer governance is typically the multi-week-to-multi-month pacing item.

> open.epic + 6b.health Vendor Services explainer + Fierce Healthcare, 2022-2026, https://open.epic.com/ and https://6b.health/insight/what-is-epic-vendor-services/ and https://www.fiercehealthcare.com/health-tech/epic-plans-overhaul-its-app-market-opens-new-connection-hub-developers-here-are-key

### Epic write-back is possible only through narrow pathways: flowsheets, documents, questionnaires
*[moderate]*

You cannot place orders or push arbitrary data into Epic through open APIs. Supported write pathways: filing device/patient-generated observations to flowsheet rows (the standard RTM route — wearable-derived vitals land in a flowsheet the care team sees), submitting documents (e.g., PDF reports via DocumentReference.Create), and posting QuestionnaireResponse for PRO instruments. Each requires the customer to build/map the target (flowsheet IDs are per-organization). This matches our need: we can push composite deviation summaries and PROMs into Epic, but CarePlan/ServiceRequest writes are out.

> open.epic Technical Specifications + integration guides, 2025-2026, https://open.epic.com/TechnicalSpecifications and https://arkenea.com/blog/integrating-healthcare-app-with-epic-ehr/

### Oracle Health (Cerner): Code Console + Ignite FHIR R4, per-customer opt-in via Service Request; registration is not go-live
*[moderate]*

Oracle Health's developer portal is Code Console (formerly Cerner Code); Ignite APIs expose FHIR R4 and legacy DSTU2 on Millennium, SMART on FHIR launch, system (Backend Services) apps, and Bulk Data Access. Each customer must opt in through a 'Cerner Ignite APIs for Millennium' Service Request in their own environment — same per-customer gating pattern as Epic. Fee schedule is not publicly published; Oracle has publicly positioned API access for data exchange as free following its 2023 'open API' announcements, but partner-program terms are contract-specific. Oracle also stood up its own QHIN (Oracle Health Information Network).

> Oracle Millennium Platform API docs, 2024-2026, https://docs.oracle.com/en/industries/health/millennium-platform-apis/fhir-app-provisioning/ and https://docs.oracle.com/en/industries/health/millennium-platform-apis/mfbda/bulk_data_access.html

### athenahealth Marketplace: no listing fee, but 15–30% revenue share and %-of-collections API pricing
*[moderate]*

athenahealth's Marketplace (800+ solutions) has no fee to list, but Marketplace Partner agreements typically take 15–30% of revenue generated through the channel; production API access for practice customers is priced as a percentage of monthly collections rather than fixed API fees. Three access tiers exist: Developer/Preview (free sandbox), Production API Access, and Marketplace Partner. All access is OAuth 2.0. athenahealth is strong in ambulatory/private-practice ortho, so it matters for community orthopedic groups even though revenue share is steep for a monitoring product.

> athenahealth Marketplace program pages + APIs.io plan listings, 2024-2026, https://www.athenahealth.com/solutions/marketplace-program and https://apis.io/plans/athenahealth/athenahealth-plans-pricing/

### ModMed (Modernizing Medicine): the dominant specialty-ortho ambulatory EHR has a certified FHIR R4 API plus a gated proprietary write API
*[moderate]*

ModMed EMA has one of the largest orthopedics-specific ambulatory footprints (specialty-specific exam/documentation structures). Its synapSYS platform offers: (a) the ONC-certified FHIR R4 API (g)(10) — read access, SMART on FHIR, documented in the July 2024 MMI Certified FHIR API doc, portal at portal.api.modmed.com; (b) a proprietary API with create/update operations covering EMA and Practice Management — but that requires a vendor application, API terms acceptance, and a partnership evaluation before access; and (c) traditional HL7 interfaces. For a post-op ortho RTM product, ModMed is arguably the second integration to build after Epic because community ortho surgeons disproportionately run EMA.

> ModMed synapSYS press release + MMI Certified FHIR API Documentation July 2024, https://www.modmed.com/press-release/modmed-synapsys-healthcare-interoperability/ and https://portal.api.modmed.com/

### CMS-0057-F: payer FHIR APIs land Jan 1, 2027 — Provider Access API is a future data channel for us
*[strong]*

The CMS Interoperability and Prior Authorization Final Rule (CMS-0057-F) requires impacted payers (MA, Medicaid/CHIP FFS and managed care, QHP issuers on FFEs) to meet operational requirements from Jan 1, 2026 (prior-auth decisions within 72 hours expedited / 7 calendar days standard, with specific denial reasons) and to run four FHIR APIs by Jan 1, 2027: enhanced Patient Access (adding prior-auth data), Provider Access (in-network providers pull claims, clinical/USCDI data, and prior-auth info for attributed patients), Payer-to-Payer, and Prior Authorization (PARDD). For our platform, the Provider Access API — accessed on behalf of our surgeon customers — becomes a payer-side route to encounter/claims history (e.g., detecting ED visits and readmissions) starting 2027.

> CMS-0057-F final rule + CMS overview page, 2024-2026, https://www.cms.gov/initiatives/burden-reduction/overview/interoperability/policies-regulations/cms-interoperability-prior-authorization-final-rule-cms-0057-f

### TEFCA in 2026: ~10 designated QHINs; Epic Nexus alone covers 1,000+ hospitals; Treatment-purpose queries require genuine provider standing
*[strong]*

Designated QHINs include eHealth Exchange, Health Gorilla, Epic Nexus, MedAllies, KONZA, CommonWell, Netsmart, eClinicalWorks (PrismaNet), Surescripts, and Oracle Health Information Network. Epic reported 41% of its customers live on Nexus by mid-2025 (1,000+ hospitals, 22,000+ clinics), 43% implementing. TEFCA supports six exchange purposes; Treatment-purpose query responses are mandatory for participants, but a monitoring-software vendor only gets Treatment standing by participating under/with an actual provider (our surgeon customers) via a QHIN or participant — the Epic-vs-Particle history shows purpose-of-use claims get audited. Carequality remains a separate non-QHIN framework in managed transition toward TEFCA alignment; CommonWell is both a legacy network and a QHIN.

> Sequoia Project RCE QHIN directory + Epic Nexus announcement, 2025-2026, https://rce.sequoiaproject.org/qhins/epic-nexus/ and https://www.epic.com/epic/post/over-1000-hospitals-connect-to-tefca-with-epic-nexus/

### TEFCA Individual Access Services (IAS): patient-mediated FHIR pull from every Epic Nexus participant — the cheapest scalable EHR channel
*[strong]*

An IAS app participating in TEFCA through any QHIN can query all Epic Nexus participants: patient completes IAL2 identity verification per the IAS v2.1 SOP, then authenticates per-organization with their MyChart credentials (OAuth 2.0); the app registers with Epic Nexus (HomeCommunityIDs, redirect URIs, JWK Set URL, RS256/384/512 or ES256/384 JWTs, active RCE Directory listing) and then calls patient.$match plus any USCDI v1 and v3 R4 FHIR APIs. Data comes back as structured FHIR, not just C-CDA documents. Patient discovery must use XCPD queries, not directory scans. Epic's 'MyChart Central' (late 2026) will further consolidate patient-mediated aggregation. This is a consent-clean, per-customer-approval-free pathway for a post-op RTM app whose patients are already enrolled.

> open.epic TEFCA IAS documentation, 2025-2026, https://open.epic.com/Home/Interoperate/TEFCA/IAS

### Aggregator pricing reality: Particle ~$60k/yr + per-query; Flexpa published tiers from $20k/yr; Health Gorilla/Metriport/Zus custom-quoted
*[moderate]*

Particle Health (network-query API over Carequality/eHealth Exchange et al.) runs roughly $60,000/year plus per-query fees. Flexpa (claims via CMS Patient Access APIs, not clinical EHR data) publishes exact tiers: Startup $20k/yr (≤5,000 users, 1,000 IAL2 verifications, 36,500 retrievals, $5/user overage), Growth $50k, Scale $130k, Omni $350k, Infrastructure $900k+. Health Gorilla (itself a QHIN, Patient360 API) does not publish rates — custom pricing. Metriport is open-source (self-hostable) with hosted pricing sales-gated; it wraps CommonWell/Carequality access and converts C-CDA to FHIR. Zus Health and 1upHealth are likewise custom-quoted. Aggregators front-load network access but you inherit their treatment-purpose eligibility review: Epic cut Particle's Carequality connection in March 2024 over purpose-of-use disputes, and Particle filed an antitrust suit against Epic in Sept 2024 — an existential channel risk to price in.

> Out-Of-Pocket Particle analysis + Flexpa pricing page + Medblocks/Slashdot comparisons, 2024-2026, https://www.outofpocket.health/p/particle-health-and-pulling-patient-data and https://www.flexpa.com/pricing

### HL7v2 ADT feeds are the reliable readmission-detection signal; hospitals are federally required to send them
*[moderate]*

CMS Interoperability and Patient Access rule (CMS-9115-F) made ADT e-notifications a hospital Condition of Participation effective May 1, 2021: hospitals with EHRs must send admission/discharge/transfer notices (HL7v2 ADT A01 admit, A03 discharge, A04 registration/ED, A08 update) to established care providers and practice groups that request them. Intermediaries — Bamboo Health Pings (formerly PatientPing), PointClickCare/Audacious Inquiry ENS, state HIEs, or Redox — deliver these as webhooks/FHIR so you avoid per-hospital MLLP/VPN plumbing; pricing is contract-based, typically per-covered-life per-month. For our infection-surveillance composite, an ED-visit or readmission ADT event is a high-specificity outcome label and an immediate risk-tier escalator, and our surgeon customers qualify as the 'established care practitioner' entitled to receive them.

> CMS-9115-F Condition of Participation (2020, effective May 2021), https://www.cms.gov/ + Bamboo Health Pings product pages, https://bamboohealth.com/

### Apple Health Records: patient-mediated FHIR R4 clinical records on-device, readable by our iOS app with user consent
*[weak]*

HealthKit clinical records (HKClinicalRecord) expose FHIR-encoded data pulled by the patient from 800+ US institutions (Epic, Oracle Health, athenahealth, ModMed patient portals support it): allergies, conditions, immunizations, lab results, medications, procedures, and vital signs; FHIR R4 supported since iOS 14 (DSTU2 legacy). Apps request per-category read authorization; records carry the raw FHIR JSON payload. Constraints: iPhone-only (a real limitation for a ~66-year-old arthroplasty cohort with mixed device ownership), data freshness depends on the patient's portal sync, and no server-side pull — the app must forward records to our backend. Direct developer-page verification failed during this research (Apple reorganized its healthcare pages), so treat category/institution counts as approximate.

> Apple HealthKit clinical records documentation (developer.apple.com/documentation/healthkit), verification incomplete 2026-07

### Information blocking is an enforceable lever: up to $1M per violation for EHR vendors/HIEs, provider disincentives finalized
*[moderate]*

Under the Cures Act as implemented, EHI scope expanded beyond USCDI to the full designated record set in October 2022; OIG can fine health IT developers and HIEs/HINs up to $1,000,000 per violation (final enforcement rule July 2023), and the June 2024 provider-disincentives final rule penalizes providers via MIPS/promoting-interoperability scoring. Practically: when a health system stalls our per-customer connection or a patient's access request, citing information-blocking obligations (and the patient's individual right of access) measurably accelerates approval. HTI-1 added a TEFCA 'manner' exception — an actor can satisfy a request by offering exchange via TEFCA, which further pushes traffic toward QHIN channels.

> HealthIT.gov information blocking + HTI-1 rule summary, 2023-2024, https://www.healthit.gov/topic/laws-regulation-and-policy/health-data-technology-and-interoperability-certification-program

### C-CDA parsing remains unavoidable for network-based exchange; treat it as a lossy secondary path
*[moderate]*

Carequality/CommonWell/TEFCA document exchange (XCA/XDS) still predominantly moves C-CDA R2.1 documents (CCD, discharge summary, operative note), not FHIR resources; USCDI mapping is via the C-CDA Companion Guide. Section quality varies wildly by sending system — procedure sections may carry CPT, SNOMED CT, or free text; results sections usually carry LOINC. Metriport and others monetize exactly this C-CDA-to-FHIR normalization. For us: operative notes (needed to confirm procedure/laterality/implant) frequently only exist as C-CDA/DocumentReference attachments, so an XML section parser with code-system fallback (SNOMED CT 609588000 TKA etc. -> our procedure taxonomy) is required even in a FHIR-first architecture.

> HL7 C-CDA R2.1 + USCDI Companion Guide; Metriport docs, 2024-2026, https://www.metriport.com/

### Staged, cost-aware integration plan for a post-op ortho RTM startup
*[moderate]*

Stage 0 (now, ~$0 licensing): register free on open.epic and Oracle Code Console; build one SMART Backend Services client (JWT/JWKS) and one SMART standalone-patient-launch flow; ship patient-mediated ingestion (Apple Health Records forwarding + MyChart standalone launch) for enrolled patients — no health-system approval needed. Stage 1 (first 1-3 provider customers, ~$2k-5k/yr): per-customer Epic Backend Services connections under each surgeon group's sponsorship (read Condition/Procedure/Encounter/Observation/DocumentReference; write flowsheet vitals + QuestionnaireResponse PROs); optionally Epic Vendor Services at $1,900/yr; start ModMed partnership evaluation for community ortho. Stage 2 (readmission signal): contract ADT notifications via Bamboo Pings/state HIE under customer provider NPIs. Stage 3 (scale, >$60k/yr justified): either TEFCA IAS participation via a QHIN for consent-clean patient-mediated national pull, or a treatment-purpose aggregator (Health Gorilla as QHIN is the most defensible; Particle cheapest to start ~$60k/yr) — choose after measuring what fraction of enrolled patients Stage 0/1 already covers. Defer CMS-0057-F Provider Access API work to 2027.

> Synthesis of sources above, 2026


## Implications for backend

- Canonical model: extend the existing provider-agnostic Observation store with FHIR R4/US Core-shaped tables for Condition, Procedure, Encounter, MedicationRequest, and DocumentReference; key procedures by SNOMED CT and CPT (e.g., CPT 27447 TKA, 27130 THA, 29888 ACL reconstruction, 29827 rotator cuff repair) and map them to the existing per-procedure expected-recovery-curve registry so EHR-confirmed procedure+date can auto-initialize a patient's baseline window and surgery-day anchor.
- Ingestion pattern: do NOT build on Bulk $export (Epic ~1,555-2,500 resources/min, no _since); build one SMART Backend Services client (RS384/ES384 JWT, hosted JWKS, system/*.rs granular scopes) doing scheduled per-patient incremental reads with _lastUpdated windows, and reuse the existing webhook-style idempotent upsert — dedupe key should be (source system identifier/OID, resource type, resource id, meta.versionId).
- Normalization layer: all three channels (direct FHIR, TEFCA IAS FHIR, C-CDA documents from network exchange) must converge into the same canonical store; budget for a C-CDA R2.1 XML section parser with LOINC/SNOMED/CPT code-system fallback because operative notes and outside-hospital records arrive as DocumentReference attachments, not structured resources.
- Gating and risk tiers: treat EHR-derived data as episodic, not continuous — the coverage/confidence gate should score EHR channels separately from wearable streams; add typed reason codes for EHR-sourced events (ADT_READMISSION, ADT_ED_VISIT, NEW_ANTIBIOTIC_RX from MedicationRequest, WOUND_CULTURE_ORDERED from ServiceRequest/DiagnosticReport) feeding the infection-surveillance composite as high-specificity discrete signals rather than EWMA inputs.
- Write-back scope: plan Epic write-back only via flowsheet observation filing (per-customer flowsheet row mapping table in config), DocumentReference.Create for weekly summary PDFs, and QuestionnaireResponse for PROs (KOOS/HOOS/ASES); do not design any CarePlan/ServiceRequest write path.
- Cost/licensing envelope: Stage 0-1 runs on $0-5k/yr (free Epic/Oracle APIs + optional $1,900/yr Epic Vendor Services); an aggregator adds ~$60k+/yr (Particle-class) and carries treatment-purpose termination risk, so instrument what fraction of enrolled patients are covered by patient-mediated + direct connections before committing; Lambda-side, per-patient incremental FHIR polling fits the existing AWS Lambda deployment better than long-running bulk jobs (15-min Lambda cap would break $export polling loops anyway).
- Only USCDI v3 data classes are guaranteed from certified EHRs in 2026 — schema fields for anything v4/v5-only (e.g., richer functional status) must be nullable and channel-annotated until ~2028.

## Open questions

- Final status of HTI-2/HTI-3 provisions under the current administration: is the USCDI v4 certification mandate (proposed Jan 1, 2028) still on track, or deregulated? Direct verification of the Dec 2024 final-rule scope was incomplete.
- Exact current terms and cost of ModMed's proprietary API partnership evaluation and whether its certified FHIR API supports Backend Services (system) clients or only user-launched SMART — load-bearing for the community-ortho segment.
- Whether a post-op RTM vendor can obtain TEFCA Treatment-purpose standing as a sub-participant under its surgeon customers (vs. only IAS), and which QHIN offers the cheapest sub-participant onboarding for a startup.
- Current Oracle Health fee schedule for production Ignite API partner connections (publicly claimed free for data exchange, but partner-program contracts are opaque).
- Apple Health Records current institution count, background-delivery behavior for clinical record types, and Android-side equivalent (CommonHealth) coverage — the Apple developer pages 404'd during research; this matters given the ~66-year-old cohort's device mix.
- Bamboo Health Pings actual per-covered-life pricing and minimums for a sub-1,000-patient panel, vs. going through a state HIE for ADT notifications.
- Health Gorilla Patient360 pricing and whether its QHIN status materially lowers treatment-purpose termination risk relative to Particle post-Epic-dispute.
- Epic's timeline for supporting _since on Bulk Data export, which would change the ingestion calculus for larger cohorts.