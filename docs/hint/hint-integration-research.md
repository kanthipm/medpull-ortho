# Hint integration research

Researched 2026-11-12 from Hint's public developer docs, support articles, terms, Google and AWS docs, and an inventory of our own code. Companion to `hint-clinic-call-context.md`, which holds what we promised.

Nothing here has been tested against a Hint sandbox. Items marked **(untested)** are read from docs only; items marked **(unknown)** could not be found.

## 1. Verdict on each promise

| Promise | Achievable? | How |
|---|---|---|
| Patient emails filed to the right chart in Hint | **Yes**, into the Interactions feed | Hint API "document interaction" per email, with attachments |
| Email "lives on the Hint side" in the Communications > Email tab | **No documented path** | The API has no communications endpoints. It will show under Interactions, not the Email tab |
| Spoken bilingual intake that walks the patient through questions | **Yes, but it must be rebuilt for the web** | Our intake is an Android tablet app; a patient at home cannot use it |
| Intake result goes "directly into the EMR" | **Yes** as a document in the chart | Document interaction with a formatted summary and PDF |
| Intake populates medications automatically | **Yes** | Hint API creates medications and supplements |
| Intake populates conditions, allergies, family and social history automatically | **Not through any documented API** | See section 4 for the three fallbacks |
| "We integrate over HL7" | **No** | Hint has no HL7, FHIR or Direct interface, and we have no HL7 code. It is a REST/JSON API |
| GLP-1 monitoring demo | **Partly built** | Sleep, HRV, VO2 max are ingested today; weight, BP, glucose, manual entry and rating scales are not |

Two things can stop the whole plan and both need an answer from the doctor this week:

1. **Her Hint plan.** API access is a paid add-on that Hint does not offer on the Launch plan. She said she pays about $300 a month; Launch is $290. If she is on Launch she must move to Pro ($320 a month for one clinician and 100 members, then $36 per extra 50 members) and pay the add-on, whose price is shown only inside her account.
2. **Her email account.** If the address patients use is a consumer @gmail.com account, Google will not sign a BAA for it and we cannot lawfully process that mailbox. She would need Google Workspace first.

## 2. How Hint lets us in

### The fast route: practice-enabled API access

- A practice admin turns it on at **Admin > Developers > Get Started**. A sandbox practice is created immediately.
- Live keys unlock when she click-signs Hint's API Access Agreement. That agreement expects a BAA between her and any software vendor she lets use the key.
- No marketplace listing, application or Hint review is involved. She adds us to her developer team (Admin > Developers > Team), which gives us the sandbox without live patient data.
- Base URLs: `https://api.hint.com` (live), `https://api.sandbox.hint.com` (sandbox). Auth is `Authorization: Bearer <key>`. Practice data lives under `/api/provider/*`.
- Limits: 20 requests a second, 500,000 a day. Pagination is `limit` (max 100) and `offset`.

**(untested)** Whether a practice-issued key reaches every clinical endpoint below. Hint's lab guide says "partners and practices with API Access", which suggests yes. First sandbox task is to confirm it.

### The slow route: marketplace partner

Application form (needs one DPC practice as a referral; she is ours), scoping meeting, commercial approval, signed Integration Partner Agreement, build, Hint testing, then a beta "typically several weeks". Fees and revenue share are not published. Worth starting in parallel because it is the only way to get an embedded panel inside Hint's UI and to serve more practices without each buying the add-on. It is not a path for next week.

Apply at https://www.hint.com/partnership-app. Technical questions go to devsupport@hint.com.

### What the API can do in the chart

| Chart area | Read | Write | Endpoint |
|---|---|---|---|
| Patient demographics, email, phones, DOB, preferred language | Yes | Yes | `/provider/patients` |
| Patient matching by name + email, DOB, phone | Yes | n/a | `POST /provider/patients/matching` (first and last name required) |
| Interactions feed: documents | Yes | Yes | `POST /provider/patients/{id}/interactions/document` |
| Interactions feed: clinical notes | Yes | Yes | `.../interactions/clinical_note` |
| Interactions feed: labs | Yes | Yes | `.../interactions/lab` |
| Medications, supplements | Yes | Yes (no delete for medications) | `.../medications`, `.../supplements` |
| Completed Hint forms | Yes | No | `GET .../form_responses` |
| Files on an interaction | PDF only, 5-minute signed URL | Via the interaction | `.../interactions/{id}/files/download_urls` |
| Conditions, allergies, family history, social history | No | No | none documented |
| Communications panel (chat, email, SMS, calls) | No | No | none documented |
| Tasks, sticky note, health maintenance | No | No | none documented |

Details that shape the build:

- **Document interaction fields:** `status` (required: `draft`, `signed`, `addended`, `deleted`, `failed`), `title`, `body` (Markdown), `event_timestamp`, `files[]`, `integration_record_id`, `integration_web_link`. Files are given as an https URL or an inline `data:` URI; Hint fetches them during the request. There is no category or practitioner field.
- **`integration_record_id`** is where we store our own id, which makes re-runs safe and lets us find what we filed.
- **`integration_web_link`** gives her a link from the chart item back to our console.
- **The interaction list filter includes `email` as a type** (`note`, `phone_call`, `email`, `lab`, `fax`, `rx`, `erx`, `vitals`, `document`, `referral`, `order`), but no endpoint creates one. Ask Hint whether an email-type interaction can be created; it would be the closest thing to "lives in Hint as email".
- **Patient list cannot be filtered by email.** For matching we either call the match endpoint (which needs a name) or sync all her patients into our database and match locally. With a solo practice the full sync is a few hundred rows.
- **Webhooks cover patients, memberships and invoices only.** `patient.created` is useful (new sign-up, send intake). Nothing fires for forms, notes or interactions, so anything clinical is polled.
- **Hint is not ONC-certified** (no listing on the federal certified-product list), so there is no standard FHIR patient API to fall back on.

### What is off the table

Hint's terms of service (July 2026) prohibit sharing account access with a third party and prohibit "any robot, spider, or other automatic device" on the service without written consent. A headless browser bot typing into the Health Summary would breach her contract with Hint. Our old Playwright form-filler experiment is therefore not a usable fallback unless Hint agrees in writing.

Side note for her: if the VA signs in with the doctor's own login today, that already breaches the same clause. Every Hint plan includes unlimited user seats with roles, so the fix costs nothing.

## 3. Priority 1: email into the chart

### What nobody else does

Hint's own support article says replies to chart emails "do not come back into the Hint patient chart". Spruce, the competitor she named, syncs only demographics and tags with Hint; no message content reaches the chart. A working email-to-chart flow is a real gap.

### Google prerequisites

- Gmail is covered by Google's BAA only on Google Workspace. The admin accepts the BAA in the Admin console. Business Starter is $7 per user a month.
- If she is on consumer Gmail: create Workspace on her practice domain, accept the BAA, and use the Admin console import tool to copy her mail and labels across. Her patient-facing address changes, which makes this the natural moment to introduce a dedicated patient address.
- For one customer we avoid Google's app verification entirely: create the Google Cloud project **inside her Workspace organisation** with the consent screen set to "Internal". No review, no security assessment, no 7-day token expiry. A public app with the same permissions needs verification plus an annual third-party security assessment and takes weeks.
- Permission to request: `gmail.modify` (read, label, move to trash). Do not request the full-mailbox scope; it is only needed for permanent delete, which we should never do.
- Tokens are revoked when she changes her password, so the console needs a visible "reconnect Gmail" state and an alert.

### Recommended design for week one

1. **Sync her Hint patients** (id, names, email, phones, DOB) into our database nightly and on `patient.created`.
2. **Poll her mailbox** every one to two minutes with Gmail's incremental history call. Skip push notifications for now; Google says they can be dropped and need a fallback poll anyway.
3. **Store the raw message** (full MIME with attachments) in S3 under the clinic encryption key before doing anything else.
4. **Match the sender to a patient.** Auto-file only when all three hold:
   - the email passes sender authentication (Gmail's `Authentication-Results` header shows DMARC pass, or DKIM pass aligned with the From domain);
   - the From address matches exactly one Hint patient;
   - it is not a forward or a mailing-list message.
   Everything else goes to a review queue in our console: unknown senders, addresses shared by family members, failed authentication, non-patient mail. She or the VA assigns or dismisses with one click, and an assignment teaches the matcher that address.
5. **File to Hint** as a document interaction: title `Email from patient: <subject>`, `event_timestamp` set to the sent time, the message text as the Markdown body, and a PDF rendering plus original attachments as files. Use the Gmail message id as `integration_record_id` so nothing is filed twice. One interaction per message keeps the feed chronological; threading by subject can come later.
6. **Verify, then label.** Read the interaction back from Hint, confirm the files are present, then apply a Gmail label such as `Filed to Hint`. That label is the only change we make to her mailbox at first.
7. **Deletion is a separate, later switch.** After a soak period she turns on "move filed mail to trash after N days". Trash auto-purges after about 30 days, giving a recovery window. This needs her explicit sign-off; it is the one destructive step.

**(untested)** Whether filed documents are visible to the patient in the portal. Responses carry a `patient_access` flag. A misfiled email that is patient-visible is a privacy breach, so check the default in the sandbox and consider filing as `draft` until she trusts the matcher.

### Backlog

About 15 months of mail, partly labelled per patient by the VA. Run it through the same pipeline, reading by label and using the label as the patient hint. Gmail quota allows roughly twenty thousand messages in a few hours. Our database is a single SQLite file in S3 behind a write lock, so the import should batch its writes or keep import state in its own store.

### The other shape: a dedicated patient address

An address on a domain we control (for example `care@<practice>.medpull.app`), received by Amazon SES, written to S3, processed by the same pipeline. SES inbound is covered by AWS's HIPAA program and adds authentication results to every message. Limit is 40 MB a message.

This needs nothing from Google and is the shape that scales to many practices. It does not help with the patients who keep writing to her old address, so for her we need the Gmail reader regardless. Suggested order: Gmail reader first, dedicated address second.

### Outbound

She sends from Hint and replies arrive in Gmail. With the reader in place those replies get filed, which closes the loop without changing how she sends. No outbound work is needed in the first build.

### HIPAA notes

- Patients may choose to email unencrypted; HHS guidance permits it with reasonable safeguards. That covers transmission. Storage and processing still need BAAs: Google (Workspace), AWS, us with her, and any model vendor.
- Our backend currently sends patient names to Groq, and our own design doc records that the Groq tier we use is outside its BAA. No real email or intake content may go through that path. Amazon Bedrock is on AWS's HIPAA-eligible list and is the simplest replacement for anything that reads PHI. Matching and filing in step 4 and 5 need no model at all.

## 4. Priority 2: intake into the chart

### What we have

- The intake product is the Android tablet app in `MedPullKioskKanthi/MedPullKiosk` (Kotlin, last commit 2026-07-10). It reads questions aloud and listens using the tablet's built-in speech engines, supports eight languages chosen up front, and has form definitions in JSON with Spanish text per field.
- `app/src/main/assets/schemas/coastal_gateway_intake.json` already covers conditions, family history, tobacco and alcohol, surgeries, medications and allergies.
- It writes to a local file, a PDF or a FHIR export. It has no web version, no mid-form language button, and its own notes list unencrypted on-device PHI as a production blocker.
- `medpull-ortho` has voice in the patient web app (`patient-web/src/core/speech.ts`), English only, and no translations anywhere.

### What to build

A web intake in `patient-web`, opened from a tokenised link (the same pattern as the existing web check-in at `backend/app/api/checkin.py`), so a new patient can do it at home on a phone:

- Port the JSON form schema and its Spanish strings from the kiosk repo; rebuild it around her revised intake form once she sends it.
- Browser speech for reading questions aloud and for dictated answers, with an EN/ES button that switches mid-form. Browser speech recognition is uneven on iPhone Safari; a typed answer must always work, and a server-side speech service under a BAA is the upgrade if quality is poor.
- Trigger: Hint's `patient.created` webhook tells us a chart exists; we text or email the link. Whether she still sends her two agreements from Hint, or we carry them, is her call.

### Getting the answers into Hint

What the API allows today:

1. **Document interaction** with the full intake as a clean, sectioned summary (Markdown body plus an "official" PDF), in English with the patient's original Spanish answers kept alongside.
2. **Medications and supplements** created as structured records (`product_name` required; strength, unit, start date, status optional). These appear in her medication list.

Conditions, allergies, family history and social history have no endpoint. Three ways to close that, in order of preference:

- **A. Ask Hint.** Email devsupport@hint.com asking whether conditions and allergies can be written, or are planned. The marketplace launched in April 2026 and the API is clearly growing (the current version is dated 2026-07-01).
- **B. Test the note sync (untested).** Hint's November 2025 release says conditions, allergies and medications documented in a visit note sync to the Health Summary. If a clinical note created through the API triggers the same sync when she signs it, that is a one-click route. Try it in the sandbox on day one.
- **C. A review-and-apply screen.** Our summary lists each proposed condition (with a suggested ICD-10 code), allergy and history item. She confirms in our console, then enters them in Hint from a side-by-side view. This is slower than promised but faster and cleaner than the VA, and it gives her the review step she will likely want anyway before anything enters the record.

Not an option: having a script submit her Hint form or type into the Health Summary. That breaches the automation clause.

**Expectation to reset with her:** "populates the health summary automatically" is true for medications today and depends on Hint for the rest. Better to say so before the on-site visit than to be found out during it.

### ICD-10

No code set exists in our repos. The National Library of Medicine's free ICD-10-CM search API is already noted in `docs/backend-design/research/datasources--VERIFICATIONS.md`. Suggested codes should be presented for her confirmation, never written as fact.

## 5. Priority 3: GLP-1 monitoring demo

| She asked for | State today |
|---|---|
| Sleep, HRV, movement | Ingested through Junction |
| VO2 max | Ingested by the iOS app from Apple Health |
| Weight from a Bluetooth scale | Metric defined, never pulled (Junction body data is not mapped) |
| Blood pressure, with manual entry | Metric defined, never pulled; tasks only ask "did you do it?" and cannot take a number |
| Glucose from a CGM | Dexcom declared in the capability table, never pulled |
| Energy, mood ratings | Exist for personal-tier subscribers only (`personal/logs.py`) |
| Sleepiness scale (Epworth) | Does not exist |
| Nutrition and activity goals | Do not exist |
| Trainer exercise calendar | Exists (the HIRT schedule build) |

The care engine already has display cards for weight trend, blood-pressure control and glucose time-in-range (`engine/care/catalog.py`), so the gap is data in, not display. For a demo, the shortest route is numeric entry on check-in tasks (weight, BP), the Epworth questionnaire as a question set, and energy and mood opened to clinic patients, on seeded data. Device ingestion can follow.

## 6. Work order

**Today, no code**

1. Ask the doctor: which Hint plan is she on, and is her patient email address consumer Gmail or Google Workspace?
2. Ask her to enable API Access (Admin > Developers) and add us to the developer team, so we get a sandbox. She sees the add-on price before confirming; the call notes say she is happy to pay Hint's integration fee.
3. Email devsupport@hint.com: can a practice key create document and clinical-note interactions; can conditions and allergies be written; can an email-type interaction be created; do API-created documents default to patient-visible.
4. Submit the partner application with her as the referral.
5. Prepare the BAA for Kanthi to bring. It is required by Hint's API agreement before we touch live data, and by HIPAA regardless.

**Sandbox day one**

- Create a patient, post a document interaction with a PDF, post a medication, read both back.
- Try the clinical-note-to-Health-Summary sync.
- Check `patient_access` on created documents and how they look in the chart and the patient portal.

**Build (medpull-ortho)**

- `Patient.email` and a Hint patient id column; a Hint client and patient sync; `hint` in the connector registry.
- Email: Gmail connect flow, poller, raw store, matcher, review queue in the console, Hint filer, label step. Add `email` to the message channel and attachment source enums.
- Intake: web form in `patient-web` from the kiosk schema, EN/ES, speech, summary and PDF, Hint document plus medications.
- Move any model call that sees PHI off Groq before live data arrives.

**What "ready by end of next week" can honestly be**

A sandbox demonstration of both flows end to end with synthetic patients, plus her live mailbox being read into the review queue if Workspace and the BAAs are in place. Live filing into her real charts depends on her plan, the add-on, the signed agreements and Hint's answers.

## 7. Still unknown

- The API Access add-on price, and her current plan.
- Whether her mailbox is consumer Gmail.
- Whether practice keys reach all clinical endpoints, and who is shown as author on API-created items.
- Default patient visibility of API-created documents.
- Whether notes created by API trigger the Health Summary sync.
- Partner program fees, revenue share and total review time.
- File size limits on document interactions.
- Hint's roadmap and changelog are behind customer login; she can read them and check for email threading or new API areas.

## 8. Sources

Hint developer docs
- https://developers.hint.com/llms.txt (index of every guide and endpoint)
- https://developers.hint.com/docs/requesting-a-sandbox-and-api-access
- https://developers.hint.com/reference/making-requests
- https://developers.hint.com/reference/webhooks
- https://developers.hint.com/reference/documentinteractioncreatedocumentinteraction
- https://developers.hint.com/reference/clinicalnoteinteractioncreateclinicalnoteinteraction
- https://developers.hint.com/reference/patientmatchpatients-1
- https://developers.hint.com/reference/formresponselistallformresponses-1
- https://developers.hint.com/reference/interactionlistallinteractions
- https://developers.hint.com/docs/prescriptions-and-medications
- https://developers.hint.com/docs/downloading-interaction-files
- https://developers.hint.com/docs/become-a-partner
- https://developers.hint.com/docs/integration-activation
- https://developers.hint.com/docs/building-an-app

Hint product, support and legal
- https://www.hint.com/pricing
- https://www.hint.com/api-access-agreement
- https://www.hint.com/partner-agreement
- https://www.hint.com/hubfs/terms.pdf
- https://support.hint.com/en/articles/9038934-send-emails-from-patient-chart.md
- https://support.hint.com/en/articles/2138128-spruce-health-integration.md
- https://support.hint.com/en/articles/8944273-intake-forms-2-0.md
- https://support.hint.com/en/articles/10716249-view-and-send-faxes.md
- https://support.hint.com/en/articles/11333334-ccda-import.md
- https://blog.hint.com/product/november-25-product-update-smarter-notes-simpler-billing-more-emr-control
- https://blog.hint.com/newsroom/unified-experience

Google
- https://knowledge.workspace.google.com/admin/compliance/hipaa-compliance-with-google-workspace-and-cloud-identity
- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification
- https://support.google.com/cloud/answer/13464323
- https://developers.google.com/workspace/gmail/api/guides/sync
- https://developers.google.com/workspace/gmail/api/guides/push
- https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/delete
- https://workspace.google.com/pricing

AWS and HHS
- https://aws.amazon.com/compliance/hipaa-eligible-services-reference/
- https://docs.aws.amazon.com/ses/latest/dg/receiving-email-concepts.html
- https://docs.aws.amazon.com/ses/latest/dg/quotas.html
- https://www.hhs.gov/hipaa/for-professionals/faq/570/does-hipaa-permit-health-care-providers-to-use-email-to-discuss-health-issues-with-patients/index.html

Spruce
- https://help.sprucehealth.com/article/238-email
- https://www.sprucehealth.com/pricing
