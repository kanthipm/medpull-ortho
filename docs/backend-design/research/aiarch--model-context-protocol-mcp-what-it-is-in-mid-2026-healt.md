# Model Context Protocol (MCP): what it is in mid-2026, healthcare/FHIR adoption, security posture, and whether it belongs in MedPull Recovery Copilot's architecture

## Summary

MCP is now a Linux Foundation-governed open standard (donated to the Agentic AI Foundation on 2025-12-09) with five spec revisions in ~20 months; the current revision, 2026-07-28, is a breaking redesign that removed protocol sessions and the initialize handshake, deprecated the Sampling/Roots/Logging primitives and RFC 7591 dynamic client registration, and left "tools over JSON-RPC with OAuth 2.1 resource-server auth" as the durable core. Healthcare adoption is real but thin: Medplum runs a production FHIR MCP endpoint, AWS Labs ships HealthLake/HealthOmics/Comprehend Medical servers, Aidbox has an experimental module, and several small open-source fhir-mcp-servers exist — but Epic has made no MCP commitment and is building in-house assistants (Art/Emmie/Penny) instead. The 2025 security record is grim for exactly our threat model: tool poisoning (Invariant, Apr 2025), the Asana MCP cross-tenant leak (~1,000 orgs, May-Jun 2025), CVE-2025-6514 RCE in mcp-remote (CVSS 9.6), and the postmark-mcp npm rug-pull, all instances of Willison's "lethal trifecta" (private data + untrusted content + exfiltration channel) — a trifecta that PHI makes categorically worse. Verdict: (i) MCP buys MedPull nothing for internal inference — our Groq layer is single-shot rendering of a deterministic bundle with no tool loop at all, and if tools are ever needed, Groq's OpenAI-compatible function calling inside our existing JSON-contract/guardrail pipeline is strictly simpler; (ii) exposing a read-only "MedPull MCP server" for clinicians' assistants is a plausible 2027 product play but premature today — build the REST API so a facade is a two-week wrapper later; (iii) consuming EHRs via MCP is the wrong layer — Epic integration goes through SMART on FHIR REST, and community FHIR MCP wrappers must never sit in a PHI path. Decision: adopt MCP nowhere in the product today; re-evaluate the "be a data source" facade in 6-12 months against the now-stabilizing 2026-07-28 spec.

## Findings

### Current spec is 2026-07-28; five revisions in 20 months signal ongoing churn
*[strong]*

Official revision history: 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25, and current 2026-07-28. Versioning is YYYY-MM-DD, incremented only on backward-incompatible change — meaning MCP has broken compatibility five times since launch. A formal feature lifecycle/deprecation policy (12-month minimum window, 90-day expedited path) and a deprecated-features registry were only adopted in 2026-07-28. Anything you build against 2025-06-18 (which most deployed clients, including Claude integrations, still speak) is already two breaking revisions behind.

> https://modelcontextprotocol.io/specification/versioning ; https://modelcontextprotocol.io/specification/2026-07-28/changelog

### 2026-07-28 made MCP stateless and deleted much of what made it 'more than function calling'
*[strong]*

SEP-2575/SEP-2567 removed the initialize handshake and the Mcp-Session-Id header entirely; every request now self-describes protocol version/capabilities in _meta, servers MUST implement a new server/discover RPC, and cross-call state uses server-minted handles passed as ordinary tool arguments. Server-initiated requests (sampling/createMessage, roots/list, elicitation/create) were replaced by the Multi Round-Trip Requests (MRTR) pattern via resultType:"input_required". Roots, Sampling, and Logging primitives were formally Deprecated (migration guidance: 'integrate directly with LLM provider APIs instead of Sampling'). SSE resumability (Last-Event-ID) was removed. Net: the durable core of MCP is tools + resources + prompts over stateless JSON-RPC — i.e., standardized function calling plus discovery.

> https://modelcontextprotocol.io/specification/2026-07-28/changelog (SEP-2567, SEP-2575, SEP-2577, SEP-2322)

### Transports: stdio + Streamable HTTP; HTTP+SSE deprecated since 2025-03-26 and formally lifecycle-Deprecated in 2026-07-28
*[strong]*

Streamable HTTP (single endpoint, POST with optional SSE response stream) replaced the old two-endpoint HTTP+SSE transport in 2025-03-26; 2026-07-28 reclassified HTTP+SSE as Deprecated under the new lifecycle policy (SEP-2596) and replaced the standing GET stream + resources/subscribe with a single subscriptions/listen long-lived POST stream. New HTTP work must target Streamable HTTP only. stdio remains the local-process transport and is unaffected.

> https://modelcontextprotocol.io/specification/2026-07-28/changelog ; https://modelcontextprotocol.io/specification/2025-06-18/changelog

### Authorization spec matured fast: OAuth 2.1 resource server + RFC 8707 mandatory since 2025-06-18; RFC 7591 DCR now deprecated in favor of Client ID Metadata Documents
*[strong]*

2025-06-18 classified MCP servers as OAuth 2.1 Resource Servers with RFC 9728 protected-resource metadata for AS discovery, and made RFC 8707 Resource Indicators MUST for clients (tokens audience-bound to the specific MCP server). 2025-11-25 added OIDC Discovery, incremental scope consent via WWW-Authenticate, and Client ID Metadata Documents (CIMD). 2026-07-28 deprecated RFC 7591 Dynamic Client Registration in favor of CIMD, added RFC 9207 iss-validation (mix-up attack defense), and required credentials to be keyed by issuer. Any server we expose must implement this stack; it is substantially more machinery than a REST API with API keys.

> https://modelcontextprotocol.io/specification/2025-06-18/changelog ; https://modelcontextprotocol.io/specification/2025-11-25/changelog ; https://modelcontextprotocol.io/specification/2026-07-28/changelog

### Governance and adoption: donated to Agentic AI Foundation (Linux Foundation) Dec 9 2025; industry-wide client support; official registry in preview since Sept 2025
*[strong]*

Anthropic donated MCP to the Agentic AI Foundation, a Linux Foundation directed fund co-founded by Anthropic, Block, and OpenAI, with Google, Microsoft, AWS, Cloudflare, and Bloomberg as backers; reported ~97M downloads in its first year. OpenAI (Agents SDK Mar 2025, Responses API, ChatGPT connectors), Google Gemini, and Microsoft (Windows 11, Copilot Studio, VS Code) all consume MCP — so 'the clinician's assistant speaks MCP' is a safe bet for role (ii). The official MCP Registry (registry.modelcontextprotocol.io) launched in preview 2025-09-08 with self-reported listings and community moderation only — no vetting that would make it a safe healthcare supply chain. No healthcare-specific MCP registry exists; only community 'awesome' lists.

> AAIF donation verified via multiple Dec 2025 reports; https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/

### Medplum is the most production-ready FHIR MCP server; it exposes raw FHIR CRUD
*[strong]*

Medplum hosts an official MCP endpoint at https://api.medplum.com/mcp/stream (Streamable HTTP), authenticating via 'OAuth 2.0 with the 6/18 auth spec', consumable from Claude.ai organization integrations (paid Claude plan required). Its primary tool is fhir-request — full Create/Read/Update/Delete on FHIR resources. Presented as production, no beta disclaimer. Notably it exposes generic FHIR CRUD rather than curated clinical tools, i.e., it hands the LLM a scalpel, not a workflow — a design we should NOT copy for clinician-facing access.

> https://www.medplum.com/docs/ai/mcp

### AWS ships healthcare MCP servers (HealthLake, HealthOmics, Comprehend Medical); Aidbox experimental; several small open-source fhir-mcp-servers
*[moderate]*

The awslabs/mcp monorepo has a Healthcare & Lifesciences section: AWS HealthLake MCP Server (FHIR data store CRUD/search), AWS HealthOmics, and AWS Comprehend Medical MCP servers — open-source, aimed at developer/agent tooling, not certified clinical products. Health Samurai's Aidbox (FHIR R4/R5/R6) added an explicitly experimental MCP module. Open-source: wso2/fhir-mcp-server (PyPI, SMART-on-FHIR auth), the-momentum/fhir-mcp-server, psufka/fhir-mcp-server (CRUD with human-in-the-loop confirmation) — all small, generic FHIR-gateway wrappers of unproven maturity. Firely has no verified MCP product. Nothing found from Oracle Health, Microsoft Azure Health Data Services, or Google Cloud Healthcare API as first-party FHIR MCP endpoints.

> https://github.com/awslabs/mcp ; Health Samurai articles; GitHub search via DuckDuckGo

### Epic has made no public MCP commitment; its agentic strategy is in-house assistants, not third-party agent access
*[moderate]*

Multiple targeted searches (July 2026) found no official Epic statement supporting MCP, no open.epic MCP endpoint, and no agentic-access program. Epic's UGM 2025 announcements were all first-party: Art (clinician assistant, Microsoft Dragon-based), Emmie (MyChart patient assistant), Penny (revenue-cycle agents), and the Cosmos/CoMET foundation model. Third-party programmatic access to Epic remains the certified SMART on FHIR / USCDI R4 REST APIs via open.epic. For MedPull, that means an EHR integration roadmap runs through FHIR REST + SMART launch, and any 'agent talks to Epic' capability is gated on Epic's own timeline. Treat claims that 'Epic supports MCP' as unsubstantiated.

> DuckDuckGo result sets on Epic UGM 2025 coverage; absence-of-evidence after multiple targeted queries

### Tool poisoning and rug-pull attacks are demonstrated, not theoretical
*[strong]*

Invariant Labs (2025-04-01) showed Tool Poisoning Attacks: malicious instructions embedded in MCP tool descriptions, visible to the model but hidden in client UIs, exfiltrating SSH keys/config via Cursor; the 2025-04-07 follow-up exfiltrated WhatsApp chat history and demonstrated 'shadowing' — a malicious server silently altering the behavior of a trusted server's tools (e.g., BCC'ing all emails). Rug-pull variant: server changes tool descriptions after initial approval. Mitigations (description pinning by hash, full-description display, cross-server dataflow controls) are client-side and inconsistently implemented. The spec's security-best-practices page acknowledges these classes but cannot enforce client behavior.

> https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks

### 2025 incident record: Asana cross-tenant MCP leak, mcp-remote RCE (CVSS 9.6), postmark-mcp npm backdoor
*[strong]*

Asana's hosted MCP server had a logic flaw exposing tasks/projects/files across ~1,000 organizations' tenants from 2025-05-01 to 2025-06-17 — an authorization bug in exactly the kind of multi-tenant MCP server we would have to build for role (ii). CVE-2025-6514 (JFrog, disclosed 2025-07-09, CVSS 9.6): mcp-remote 0.0.5-0.1.15 allowed a malicious MCP server to achieve OS command execution on the client via a crafted authorization_endpoint URL passed to open() (PowerShell subexpression injection); fixed in 0.1.16. Koi Security found postmark-mcp on npm: a legitimate-looking MCP server that in v1.0.16 silently BCC'd users' outbound email to the author — the first documented malicious MCP package (rug-pull in the wild). Related: CVE-2025-49596 (MCP Inspector RCE) is widely reported but was not independently verified in this session.

> https://jfrog.com/blog/2025-6514-critical-mcp-remote-rce-vulnerability/ ; BleepingComputer/UpGuard/Nudge Security on Asana; Koi Security on postmark-mcp

### The spec itself bans token passthrough and details the confused-deputy attack — directly constraining any MedPull MCP design
*[strong]*

Normative text: 'MCP servers MUST NOT accept any tokens that were not explicitly issued for the MCP server' (token passthrough anti-pattern; audience validation per RFC 9068/8707 required). The confused-deputy section requires MCP proxy servers fronting third-party APIs to implement per-client consent screens, exact redirect_uri matching, __Host- prefixed signed consent cookies, and strict OAuth state handling. New 2026-07-28 sections add SSRF (metadata URLs pointing at 169.254.169.254 etc.), state-handle hijacking ('MUST NOT treat possession of a state handle as authentication' — bind handles to the verified user), and localhost redirect-URI impersonation under CIMD. For us this means: a MedPull MCP server must be a proper OAuth resource server minting its own audience-bound tokens; it may never forward a clinician-assistant token to Groq, AWS, or a future EHR connection.

> https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices

### Lethal trifecta: PHI + untrusted content + exfiltration channels is exactly the configuration clinician-side MCP creates
*[strong]*

Willison (2025-06-16) formalized the failure mode: an agent with (1) private-data access, (2) exposure to untrusted content, and (3) outbound communication will eventually be prompt-injected into exfiltration, because 'LLMs follow any instructions that make it to the model.' MCP amplifies it by encouraging users to mix tools from many vendors in one agent. If a clinician's Claude/ChatGPT session has a MedPull MCP connection plus any web/email/other MCP tool, a poisoned document or tool description can instruct the model to pull patient data through our tools and push it elsewhere — outside our security boundary entirely. GitHub's official MCP server was exploited this way (private-repo leak via a crafted public issue, May 2025). Mitigation on our side is limited to: read-only tools, minimal fields, per-tool scopes, and audit; we cannot fix the client.

> https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/

### Role (i) verdict: MCP adds pure overhead for MedPull's internal inference — we don't even use function calling today
*[strong]*

Inspection of backend/app/llm (groq.py, provider.py) confirms the LLM layer is single-shot: the deterministic engine (backend/app/engine/pipeline.py et al.) computes every number, a bundle is rendered to prompts, output is contract-validated with deterministic fallback, and 'ask the roster' is a Python-orchestrated retrieve→verify→compose flow — no tool loop exists. MCP's value proposition (N clients × M servers interop, discovery, cross-org reuse) is zero inside a single-team monolith on Lambda; it would add a JSON-RPC hop, a second process or in-proc server, version-negotiation surface, and a fast-moving spec dependency while removing our tight control over ordering and validation. If conversational check-ins later need tool use, Groq's OpenAI-compatible tools/tool_choice parameters on llama-3.3-70b-versatile (or Anthropic native tool use) inside the existing guardrail pipeline is strictly simpler and keeps determinism.

> Codebase inspection: /Users/steve/Documents/GitHub/MedPullKioskKanthi/recovery-copilot/backend/app/llm/groq.py, provider.py; MCP value analysis from spec docs

### Role (ii) verdict: 'be a data source' is a real but premature product play; design for it, don't build it yet
*[moderate]*

Every major assistant platform can consume remote MCP servers, so a read-only 'MedPull MCP server' (worklist, patient recovery summary, roster query) is the plausible future distribution channel — Medplum proves the pattern. But today it means: implementing the OAuth 2.1 RS + RFC 8707 + CIMD stack; multi-tenant authorization done perfectly (Asana failed this); accepting lethal-trifecta exfiltration risk in clients we don't control; HIPAA exposure that depends on the clinic having a BAA with the assistant vendor (only enterprise tiers of Anthropic/OpenAI offer this), which most small ortho practices won't have; and tracking a spec that just removed sessions. With zero customers asking, the cost/risk is unjustified. The cheap hedge: keep the REST API resource-shaped and audience-authenticated so an MCP facade is a 1-2 week wrapper when a design partner demands it.

> Synthesis: Medplum docs, Asana incident, MCP auth spec, Willison

### Role (iii) verdict: consume EHRs via SMART on FHIR REST, not MCP; never put community MCP servers in a PHI path
*[strong]*

Epic/Oracle offer no first-party MCP endpoints; the regulatory rails (21st Century Cures Act info-blocking / certified USCDI FHIR R4 APIs, SMART app launch) all run over plain REST, which our deterministic connectors (backend/app/connectors) can call with pinned schemas, retries, and tests. Interposing an MCP server (AWS HealthLake MCP, wso2 fhir-mcp-server, etc.) between our backend and an EHR adds a component designed for agentic/LLM-driven access where we want deterministic ETL — and the postmark-mcp backdoor and self-reported registry show the supply chain is unvetted. MCP consumption only becomes interesting if our own agent must dynamically choose among many external tools at inference time, which contradicts our deliberately deterministic architecture.

> https://github.com/awslabs/mcp ; Koi Security postmark-mcp; Epic open.epic FHIR program

### Primitives scorecard for evaluating 'MCP vs function calling' claims
*[strong]*

Server primitives: tools (model-invoked functions with JSON Schema 2020-12 in/out, structured output since 2025-06-18), resources (URI-addressed data), prompts (user-invoked templates). Client primitives: sampling (server borrows client's LLM), roots (filesystem scoping), elicitation (server asks user for input). As of 2026-07-28: sampling and roots are Deprecated, elicitation was rebuilt as MRTR, tasks moved to an extension (io.modelcontextprotocol/tasks, polling model). So the honest comparison is: MCP ≈ provider-agnostic function calling + discovery + an OAuth profile. For a backend that already owns both sides of the tool boundary, the discovery and provider-agnosticism are worth nothing; the OAuth profile only matters when third parties connect.

> https://modelcontextprotocol.io/specification/2026-07-28/changelog ; 2025-06-18 and 2025-11-25 changelogs


## Implications for backend

- No changes to /Users/steve/Documents/GitHub/MedPullKioskKanthi/recovery-copilot/backend/app/llm/groq.py or provider.py are warranted by MCP: the single-shot bundle-render + contract-validate + deterministic-fallback design is the right architecture and needs no tool loop. When tools do arrive (conversational check-ins), add them behind the existing provider abstraction using Groq's OpenAI-compatible function calling so the fallback chain (Groq → deterministic) is preserved.
- Keep 'ask the roster' orchestration (retrieve → per-patient verify → compose) in deterministic Python rather than converting it to LLM-driven tool selection — this is precisely the control MCP-style agentic designs give up, and it is our main defense against hallucinated cross-patient claims.
- Shape the FastAPI surface now so a future MCP facade is a wrapper, not a rewrite: resource-oriented, read-only endpoints for worklist/patient-summary/roster-query returning the same guardrailed text as the UI; audience-validated tokens at the Lambda/CloudFront boundary (aws/middleware.py); per-request audit logs keyed by clinician identity and patient ID (doubles as RTM audit evidence). Never treat possession of any ID/handle as authentication — bind to the verified principal, per the spec's state-handle-hijacking guidance.
- EHR roadmap: build backend/app/connectors toward SMART on FHIR R4 REST against certified endpoints (Epic open.epic et al.), not against FHIR MCP wrappers; keep PHI movement in deterministic connector code with pinned schemas and tests.
- Supply-chain hygiene: developers may use MCP servers in their local Claude Code tooling, but no MCP package may be a runtime dependency of the Lambda; if one ever is proposed, require version+hash pinning and a security review (postmark-mcp precedent).
- If/when the MCP facade ships, it must mint its own tokens (OAuth 2.1 RS, RFC 8707 audience binding) and must never pass inbound assistant tokens to Groq, AWS services, or EHR connections — the spec makes token passthrough a MUST NOT, and with PHI it would also wreck HIPAA accounting-of-disclosures.

## Recommendation
**Do not adopt MCP anywhere in MedPull today — not for internal inference, not as an exposed interface, not for consuming external systems. Keep the deterministic-engine + single-shot Groq design; when conversational check-ins need tools, use provider-native (OpenAI-compatible/Anthropic) function calling inside the existing JSON-contract guardrail pipeline. Re-evaluate exactly one MCP role — a read-only 'MedPull MCP server' facade for clinicians' assistants — in 6-12 months, and build it only when a paying design partner's assistant platform demands it.**

MCP's benefits are interoperability benefits: N clients × M servers, tool discovery, and a shared OAuth profile across organizational boundaries. MedPull is a single-team monolith whose LLM layer deliberately does no tool calling — every number comes from the deterministic engine, and the one agentic-ish flow (ask-the-roster) is Python-orchestrated on purpose. Internally, MCP would add a protocol hop, a dependency on a spec that has broken compatibility five times in 20 months (2026-07-28 just removed sessions, the handshake, sampling, and roots), and zero capability we lack. Externally, the 2025 incident record (Asana's ~1,000-org cross-tenant leak, tool poisoning, CVE-2025-6514, postmark-mcp backdoor) plus the lethal-trifecta structure means exposing PHI through MCP into client environments we don't control is the single riskiest thing we could do at our maturity — and no customer is asking for it. On the consume side, the EHR world runs on certified SMART on FHIR REST; Epic has shown no MCP intent and is building its own closed assistants. The correct posture is REST-first with an architecture that keeps a future MCP facade cheap.

**Do NOT:**
- Do not rewrite the internal Groq/LLM layer as an MCP client-server loop, or spin up an MCP server 'for our own backend to call' — it is pure overhead for a monolith and couples us to a fast-churning spec.
- Do not install community/third-party MCP servers (fhir-mcp-server variants, registry listings, even awslabs servers) anywhere in a PHI-bearing production path — the registry is self-reported and unvetted, and postmark-mcp proved the rug-pull risk is real.
- Do not expose write-capable or free-text-action tools (draft-patient-message, modify-care-plan) over any future MCP facade — read-only monitoring data with the existing guardrail sentence only; prompt-injected clinician assistants must not be able to act on patients through us.
- Do not implement the deprecated surface if/when we do build: no HTTP+SSE transport, no Roots/Sampling/Logging primitives, no RFC 7591 dynamic client registration as the primary mechanism — target Streamable HTTP + Client ID Metadata Documents on the 2026-07-28 line.
- Do not ever accept a clinician-assistant token and forward it to Groq, AWS, or an EHR (token passthrough anti-pattern — spec-level MUST NOT); every hop mints its own audience-bound credentials.

**Sequencing:**
- 1. Now (zero effort): record this decision in the repo (ADR): no MCP in product; provider-native function calling is the sanctioned tool-use mechanism. Prevents ad-hoc MCP creep via dev tooling into the PHI path.
- 2. When building conversational SMS/app check-ins (days, not weeks): implement tool use with Groq's OpenAI-compatible tools/tool_choice on llama-3.3-70b-versatile behind the existing provider.py abstraction, keeping the deterministic renderer as fallback and all outputs behind the JSON-contract + banned-language validators. Keep question-flow branching deterministic (recovery-stage state machine); use the LLM only to phrase, not to route.
- 3. Within the next quarter (~1-2 days): shape the REST API and auth to be 'MCP-facade-ready' — resource-oriented read endpoints (worklist, patient summary, roster query) that map 1:1 to future read-only tools; audience-validated bearer tokens at the Lambda boundary; per-request audit logging of who read which patient's data (needed for RTM billing audits anyway).
- 4. Quarterly (hours): re-check the landscape — Epic/open.epic for any first-party MCP endpoint, AAIF/HL7 activity on a SMART-scopes-for-MCP profile, whether the 2026-07-28 line has stabilized, and whether Claude/ChatGPT enterprise tiers with BAAs are present in our customer base.
- 5. Trigger-based (1-2 weeks when a design partner asks): ship a read-only MedPull MCP server — Streamable HTTP on a separate subdomain, OAuth 2.1 resource server with RFC 8707 audience binding and CIMD registration, 3-5 read-only tools returning the same contract-validated text the UI shows (guardrail sentence included), per-client consent, minimal-necessary fields, full audit trail; pen-test specifically for cross-tenant authorization (Asana's failure) and injection-driven exfiltration before any real PHI flows.

## Open questions

- Will Epic (or Oracle Health) ever expose a first-party MCP endpoint, or will agentic access to Epic remain locked to Epic's own assistants (Art/Emmie) and SMART on FHIR? No signal as of July 2026; this gates any 'clinician's EHR-embedded agent queries MedPull' scenario inside Epic's chrome.
- Which spec generation will consumer assistants actually speak when we ship a facade — the 2025-06-18/2025-11-25 session-based line (what Claude.ai integrations use today, per Medplum's '6/18 auth spec') or the stateless 2026-07-28 line? Building too early risks targeting the wrong one.
- What BAA coverage do clinicians' assistant subscriptions actually have (Claude Enterprise, ChatGPT Enterprise vs consumer tiers)? If our ortho-practice customers are on consumer plans, the 'be a data source' play is HIPAA-dead regardless of our engineering. Needs customer discovery, not research.
- Will HL7/SMART Health IT publish a balloted profile mapping SMART on FHIR scopes (patient/*.read etc.) onto MCP authorization? Academic FHIR+MCP papers exist, but no standards-track artifact was found; such a profile would materially de-risk role (iii).
- Does Groq's API's remote-MCP/tool support (reported in beta during 2025) change the latency/cost calculus for tool-augmented check-in conversations on llama-3.3-70b-versatile? Unverified this session — check Groq docs before building step 2.
- CVE-2025-49596 (MCP Inspector RCE, reported CVSS ~9.4, June 2025) was cited from memory and not independently verified here — confirm before quoting it externally.