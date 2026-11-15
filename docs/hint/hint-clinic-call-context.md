# Discovery call with Dr. DeVries: context for the build

This file is the full context from a 45-minute discovery and demo call with a prospective clinic customer. It exists so that Claude Code can understand what we need to build, why, and what is still unknown.

**Source.** A screen recording of the call (`~/Downloads/video.mp4`, recorded 2026-11-11 per file metadata), transcribed locally with Whisper and cross-checked against sampled video frames. The transcript has no speaker labels, so attribution is from context. Items marked *(unclear)* are best readings of imperfect audio or low-resolution frames.

**PHI warning.** The doctor screen-shared real patient charts and her Gmail, and said at the start that the call should not be recorded. No patient names or patient details are reproduced here. Do not copy any from the recording into code, fixtures, tests or prompts. Use synthetic patients only.

---

## 1. Who was on the call

| Person | Role |
|---|---|
| Dr. Abigail DeVries | Physician and owner of a solo direct primary care (DPC) practice. The customer. |
| Kanthi Makineedi | Our team. Met the doctor on the Monday before the call for fact-finding. Hosted the meeting, joined partly from a bus. Will visit the practice in person. |
| Medha Pulluru | Our team (co-founder). Led most of the questions, the product demo and the recap. |
| Steve | Our team. Not on the call; phoned mid-call for the demo console access token. |

## 2. The customer's practice

- Solo direct primary care practice, in business about 15 months.
- Licensed in North Carolina, plus a couple of other states because patients moved. Sees patients both virtually and in person.
- Patients join a monthly membership or buy individual visits on her website. That initial sign-up flow is "fairly automated".
- Patients are fairly healthy and many pay cash. A lot of her work is GLP-1 and other weight management.
- She is bilingual (English and Spanish) and wants to recruit more Spanish-speaking patients. She got a "crazy" quote for translating her policies and still needs to do that properly.
- She pays a virtual assistant (VA) for 20 hours a week at $10 an hour, so $200 a week, basically for data entry. The VA is offshore, hired through an agency. The agency has signed a BAA and the staff have HIPAA training, but the doctor still sees it as a risk because it is her patients' information.
- She is open to AI doing this work if it is safer and cheaper. She mentioned that something like "Claude Cowork that's HIPAA compliant could do that all day long".

## 3. Her current tool stack

### Hint (her EMR), about $300 a month

Hint is an EMR built for direct primary care. What she showed:

- Home page with tasks, incoming messages and a calendar.
- Google Meet embedded for visits.
- Patient chart with:
  - a sticky-note area for miscellaneous info;
  - an Interactions feed (visit notes, documents, forms, labs, faxes, prescriptions);
  - a Health Summary with two tabs: "Current Medical" (Medical Conditions, Allergies, Medications, each with Active and Resolved or Discontinued) and "General Info" (family history, social history, lifestyle questions);
  - a Tasks panel;
  - a Communications panel with tabs for Chat (secure messaging), Email, Phone Call, SMS and Log SMS.
- Website sign-up creates a chart. She then sends forms from the chart: two agreements and an intake form (she is revising the intake form).
- Custom forms. A completed form has an "Add to Health Summary" action that can route selected answers into the health summary. She finds this hard to locate and "super annoying"; the VA figured it out. Nothing is populated automatically.
- An embedded AI scribe, which she does not use because it is not as good as her alternative.
- Referrals can now be faxed directly from the chart (previously she had to download PDFs). There is no referral tracking.
- LabCorp interface for ordering labs directly. This works well.
- Patient portal with secure messaging and shared documents. Patients use an app; she sees it inside the EMR. This is fairly new and better than before.
- Calling and SMS directly from the EMR. The SMS is not HIPAA compliant; patients sign a waiver.
- Email from the chart is **outgoing only**. Patient replies go to her Gmail. Hint used to bring replies back in, broke it, and has said reconnecting it is not a priority.
- A health maintenance workflow that is entirely manual: she has to tick items off herself, with no link to lab results. She called it no better than her spreadsheet. *(The audio says "top health workflow"; the screen shows "Health Maintenance".)*
- A beta mobile app for clinicians, not great.
- An integrations marketplace of partner apps. She thinks Hint is open to partnerships, that a direct integration probably does not require a marketplace listing, and that Hint is small (her guess: under a thousand practices), so getting a demo or conversation should be quick compared with Epic.

### Other tools

| Tool | What she uses it for | Pain |
|---|---|---|
| OpenEvidence | Transcribing visits (preferred over Hint's scribe) | Copy, paste into a document, then revise by hand |
| DoseSpot | E-prescribing (third party connected to Hint) | None raised |
| Gmail | Patient email | Replies are stranded outside the chart; cannot sort by sender |
| Local imaging facility portal (name sounded like "Cardinal Points") | Imaging referrals | Re-enters demographics and insurance by hand; she has entered dates of birth wrong and had to redo orders |
| A second imaging facility portal | Rarely used | "Very archaic" |
| Epic community provider access at UNC (CareLink), Duke and WakeMed | Reviewing outside records and entering orders. No documentation is done there. | Slow logins. For a referral she creates it in Hint, makes a PDF, uploads it, enters the order, then tracks it. Results are not always faxed back, so she logs in again to fetch them. |
| A record-pull app (name sounded like "Vivlio") | Pulls outside records from a health information exchange into the chart, about $2 per pull, triggered for certain appointment types | Format is poor and nothing can be trended. She uses it to find out where a patient was seen, then logs into that Epic anyway. |
| A nationwide compounding pharmacy portal | Compounded prescriptions | Another login |
| A sleep medicine portal | Sleep referrals | Another login |
| CoverMyMeds | Prior authorizations, mostly for GLP-1s | Painful, but low volume for her |
| A basic CRM built for DPC practices | Newsletter; website contact form leads | No lead follow-up. She is ambivalent about automated nudges because daily follow-up emails annoy her as a recipient. |
| Her website | Membership and single-visit purchase, contact form | She noted it needs a clearer join button |

## 4. The problem we agreed to solve first

When asked what consumes the most time, her answer was the work she pays the VA to do. It is not her own time, but she pays $200 a week for it and it carries PHI risk. The VA does two things:

### 4a. Intake form data into the chart

1. A patient signs up on the website and a chart is created.
2. The doctor sends the two agreements and the intake form from the chart.
3. The patient completes them.
4. The VA reads the completed intake form and types the content into the chart's Health Summary: medical conditions, allergies, medications, then family history, social history and the other general info.

Before the VA, the doctor left this information sitting in the form. She said the VA's way is not exactly how she would do it, but it is better than nothing. She thinks an agent could do it more cleanly, for example by attaching ICD-10 codes to conditions.

### 4b. Patient emails into the chart

1. In the early months the portal was weak, so she emailed with patients, and she sent visit summaries by email. Patients learned her address and many still email her.
2. She does not expect to retrain them. Some like secure messaging, some text, some are "wedded to email". She wants to keep offering email.
3. Part of the medical record is therefore sitting in Gmail, which she does not like.
4. The current manual process: search Gmail for one patient, gather that patient's emails under a per-patient label, import them into the patient's chart in Hint. The VA also pulls records out of emails. The doctor is not sure exactly how the VA does each step.
5. Her eventual plan is to delete the emails from Gmail once they are in the chart.
6. She described this as "stupid work" and "agent kind of work".

She would accept either of two shapes, and said either would be "delightful":

- an agent that automatically pulls emails from Gmail into the chart; or
- a different channel where the patient still just sends an email, but it lands in an integrated platform and appears in the EMR rather than in Gmail.

## 5. What we committed to build

From Medha's recap near the end of the call.

### Priority 1: email automation (the "big priority")

- Pull patient emails into Hint, filed to the correct patient's chart.
- Have her patient email live on the Hint side, per patient, instead of only in her own inbox.

### Priority 2: intake form

- Use the intake product we have already built and connect it to Hint. As described to her on the call:
  - the patient has a spoken conversation with it and it fills in the form;
  - a button switches between English and Spanish;
  - it reads the questions aloud;
  - the patient can answer verbally in either language;
  - it walks the patient through the questions;
  - the result goes directly into the EMR;
  - it populates the health summary (conditions, allergies, medications, family and social history) automatically, with no email or manual transfer.
- She found Hint's own intake form unsophisticated and not "official" looking, and compared it unfavourably with one she filled in for her son's orthodontist. A polished patient experience matters to her.
- We promised to show or email her the existing intake demo; nobody could pull it up during the call.

### Priority 3 (future state, not urgent): GLP-1 and nutrition workflow demo

- Offered for the same delivery date so Kanthi can show everything at once. Details in section 7.

### Integration approach discussed

- Medha said our platform is built to integrate over HL7 and that we would research Hint's integration options ourselves, including taking a demo with Hint if needed. The doctor offered to find out; we declined and took it on.
- Nothing about Hint's actual API or integration capabilities was established on the call. This is the main technical unknown.

## 6. The MedPull product as demoed

Medha demoed our existing product so the doctor could see what already exists. The demo data was a physical therapy scenario (patients recovering from surgery such as ACL reconstruction and joint replacement), with an explicit note that it does not have to be post-operative.

Positioning as stated: the mission over the last year has been care between visits, bringing what happens between visits to the physician. Wearable signals are compiled for the physician, and for patients without a wearable the phone itself is the sensor. Target clinics so far are physical therapy and primary care, including care for women around menopause.

### Patient side

- A mobile app, or text messaging only for patients who do not want an app.
- The physician assigns day-to-day tasks, for example log your pain, take three short walks, do your exercises.
- Daily check-ins that collect what matters for the patient's condition.
- Metrics tuned to the condition. For ACL recovery: how evenly the patient walks, stride length, time between steps, stairs.
- Range-of-mobility measurements (described as proprietary) and gait asymmetry.
- For senior care, spotting gait deviations to anticipate falls before they happen.
- A care tab for messaging the care team or the doctor from the app.
- A patient can text a phone number and the messages are delivered into the doctor's Hint, described as HIPAA compliant. The doctor pointed out she already has texting in Hint, so this was not the gap; email is.

Seen on the app's home screen: a greeting, day count since surgery, a recovery-versus-expected chart, today's plan, a "start today's check-in" button, and tabs for today, progress, measure and care.

### Provider console

Described aloud:

- An AI summary across all patients, highlighting who needs attention. This was pitched as the quick overview of her whole list that she lacks today.
- Asking questions in plain language, for example who reported fever this week, which patients are behind schedule, which still need to come in.
- Sorting to surface patients with concerning symptoms.
- A patient chart with that patient's metrics.
- Calling the patient.
- Texting the patient, with suggested prompts such as asking about temperature.
- Assigning tasks from a library of common tasks (take your blood pressure, log your pain, stay within today's step range). Tasks appear in the app or arrive by text, whichever the patient chose.
- An escalate action that notifies the care team (more relevant to larger practices).
- Adherence: how many of the assigned exercises the patient actually did.
- A calendar, built at the request of physical therapy clinics, where exercises are dragged onto days and the patient is texted what was assigned for that day.
- Pulling data from Whoop, Oura, Garmin, Apple Watch and Apple Health.
- A physical therapy EMR integration is in progress.
- The console could be integrated into Hint.

Visible on screen but not described aloud *(read from low-resolution frames)*:

- Sign-in with a clinic access token.
- Top navigation: Worklist, Teams, Integrations, Exercises, Settings.
- "Today's briefing" text at the top of the worklist.
- Patient list filters: All, High-risk, Missing data.
- Per-patient row actions such as call the patient today, log call, ask how they are feeling, send now.
- A "build care plan" dialog with a "Build with AI" option, a searchable task library filtered by recovery phase, and an option to text the plan to the patient.
- Metric cards with trend charts and plain-language explanations.
- A "Brought to your attention" panel listing detected patterns (for example a recovery trend, a plateau or regression, an endurance fade).
- A recovery summary, a timeline of events, days since surgery, percentage against the expected curve, and time since last check-in.
- A next-steps list with actions: call, message, escalate to nurse triage, send today's check-in.
- A wearables panel showing a connected device and a connect button.
- A footer disclaimer that signals are for clinician review and are not a diagnosis.
- An "Exercise schedule" page: a week grid of patients by day with each day's exercises.

## 7. What the doctor wants from a monitoring product

Her reaction to the demo was that it could be valuable for her GLP-1 patients. Medha agreed: those patients need careful monitoring, adherence support and care when tapering off.

### Data she would want

- Sleep scores.
- Weight, from a Bluetooth-connected scale.
- HRV.
- VO2 max trends, as a general fitness indicator.
- Movement data from Apple Watch.
- Continuous glucose monitor data. Some patients wear an over-the-counter one for about two weeks.
- Blood pressure from a Bluetooth cuff. Few patients have one, so allow manual entry.
- Nutrition goals set per patient.
- Physical activity goals set per patient.
- Subjective rating scales entered by the patient and tracked over time: perceived energy level, mood, and a sleepiness scale. She is passionate about screening for sleep apnea. *(The audio is garbled; she almost certainly means the Epworth Sleepiness Scale.)*
- Built-in dietary recommendations.

She wears a Whoop herself.

### Her GLP-1 program idea

- Existing GLP-1 platforms offer a two-minute visit and the drug, nothing more.
- She wants to partner with an exercise coach and a nutrition coach to offer wraparound, holistic support alongside the medication, possibly as a national program.
- Multidisciplinary model: a trainer loads standard exercises and tailors them to the patient; a nutritionist provides baseline guidance and tailors it after talking with the patient. She would pay the trainer. It needs to feel robust.
- The drag-and-drop exercise calendar fits this.

Medha said we would look into building a demo for this and that we are exploring how the product fits different workflows.

## 8. Other pain points raised (not committed)

These came up in her walkthrough. None are in the first build, but they describe where she loses time or risks errors.

- Manual re-entry of patient demographics and insurance into outside portals for imaging referrals, with real data-entry mistakes.
- Three separate Epic community portals for records and orders, with a manual PDF upload for each referral and manual chasing of results.
- No referral tracking in Hint.
- Health maintenance items that should be checked off automatically when the lab result arrives.
- Visit transcription that needs copy, paste and revision.
- Outside records that cannot be trended.
- No lead follow-up in the CRM (she is unsure she wants it).
- Prior authorizations (low volume for her).
- Gmail cannot sort by sender.
- Spanish translation of her policies.

## 9. Competitor mentioned

**Spruce.** A communication platform widely used by DPC practices; she has resisted adopting it. Patients can email directly into it, which is the "email goes to an integrated app, not Gmail" shape. It is listed in Hint's marketplace. It does not do wearables, only communication. She suggested we look at it as a competitor. Medha's reply was that this is what we do.

## 10. Commercial terms and next steps

- **Pricing floated:** first month free, except any fee Hint charges for the integration, which the doctor said she is happy to pay. After that, about $200 a month, against her current $200 a week for the VA.
- **Delivery:** Medha first said we would likely build something and show it over the weekend, then at the recap said the email and intake pieces would probably be ready by the end of next week (the week of 2026-11-16).
- **On-site visit:** Kanthi will go to the practice in person next week, show how everything works, possibly shadow the doctor for a day while she uses it, and collect change requests, which we said we would turn around right away.
- **Paperwork Kanthi will bring:** our BAA, the trial terms on paper, the pricing model, and a conversation about what metrics the doctor would need to see before continuing.
- **Follow-up questions:** Kanthi proposed a second call for a deeper dive into the workflow. Medha preferred texting the doctor specific questions. The doctor is fine with either.
- **Owed to the doctor:** the existing intake demo, shown next time or sent by email.

## 11. Open questions before and during the build

Nothing below was settled on the call.

1. **Hint integration.** What does Hint actually expose (API, HL7, webhooks, marketplace partner program)? Can we write to the Health Summary fields, the Interactions feed and the Communications panel? Is there a fee or approval step?
2. **Where email lands in Hint.** In the Communications email tab, as a document in Interactions, or somewhere else? She was shown none of these options; she only said she wants it "in the EMR" on the patient's chart.
3. **Which shape for email.** Agent pulling from her existing Gmail, a new patient-facing address that routes into our system, or both. She is fine with either.
4. **Gmail access.** How we get authorized access to her mailbox, and whether her Google account is under a BAA with Google.
5. **Matching emails to patients.** How to match a sender to a chart, and what to do with unmatched senders, shared family addresses and non-patient mail in the same inbox.
6. **Backlog.** About 15 months of existing patient email, partly sorted into per-patient labels by the VA. Is migrating the backlog in scope, or only new mail?
7. **Deleting from Gmail.** She wants emails removed from Gmail after import. This is destructive and should require her explicit confirmation and a verified copy in the chart first.
8. **Attachments and records.** The VA "pulls records from emails". What happens to attachments, and is any content extracted into structured chart fields?
9. **Outgoing email.** She sends from Hint today and replies go to Gmail. Does the reply path need to change, or do we only ingest?
10. **Intake form content.** She is revising her intake form. We need the current and revised versions, plus the two agreements, and a decision on whether the agreements are part of our flow.
11. **Intake mapping.** Exactly which answers go to which Health Summary fields, whether she wants ICD-10 codes on conditions, and whether she reviews before anything is written to the chart.
12. **Spanish.** Whether intake answers given in Spanish are stored in Spanish, English or both, and whether her policies need translating as part of this.
13. **HIPAA.** BAA between us and her practice, BAAs with our model and infrastructure vendors, and where PHI is stored and logged.
14. **Success metrics.** What she needs to see to continue after the free month. This is to be agreed at the on-site visit.
15. **VA transition.** Whether we replace the VA entirely or run alongside for a period.
