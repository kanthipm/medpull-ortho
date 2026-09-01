# Corrections to the research corpus — verified by me, not by the agents

## C1. The "January 29, 2026 FDA CDS guidance reissue" is UNVERIFIED and probably wrong

The `aiarch--fda-regulatory...` agent's single headline claim is that FDA reissued the *Clinical
Decision Support Software* guidance on **January 29, 2026** (superseding a January 6, 2026 version,
which superseded the September 2022 final), and that the new version is **materially more permissive**
on patient-specific risk prediction — expressly listing 90-day post-operative complication risk as a
NON-device example. The agent said it verified this by downloading `fda.gov/media/109618/download`.

**I could not confirm this, and independent evidence points the other way.**

- `fda.gov` is entirely unreachable from my fetch tool (every URL, including the site root guidance
  index, returns 404 — this is bot-blocking, so it is not evidence either way about the PDF).
- The **Federal Register API** — the authoritative public record, in which FDA is required to publish
  a notice of availability when it issues or revises a final guidance — returns **no Clinical Decision
  Support Software guidance notice in 2025 or 2026**. The most recent is:
  *"Clinical Decision Support Software; Guidance for Industry and FDA Staff; Availability"*,
  **published 2022-09-28**.

**How to treat this:** assume the **September 2022 final guidance governs**, which is the *stricter*
reading, and design to it. That is the safe direction regardless of who is right: a product built to
the 2022 guidance is compliant under both readings, whereas a product built to the claimed 2026
reading is exposed if the reissue does not exist.

This matters a great deal, because the 2022 guidance is the one that treated risk scores and
probabilistic outputs far more strictly than industry expected. If the team plans a product around
"we can output a 90-day complication probability because the 2026 guidance says that is non-device,"
and the 2026 guidance does not exist, the plan is built on sand.

**Action:** have healthcare regulatory counsel confirm the current operative version before any
product decision depends on it. Do not cite the January 2026 date in a pitch deck, a data room, or a
customer security questionnaire until confirmed.

## C2. The deployment critic's TIER_ORDER claim is wrong

The methods deployment critic said to "change TIER_ORDER so MISSING_DATA never sorts below LOW."
Verified in `backend/app/api/worklist.py:14`:

```python
TIER_ORDER = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.MISSING_DATA: 2, RiskLevel.LOW: 3}
```

Lower number sorts first, so MISSING_DATA (2) **already** outranks LOW (3). The critique is already
satisfied; no change needed. Do not "fix" this.

## C3. The `GET /worklist` performance finding IS real — verified

`backend/app/api/worklist.py:34-56` loops over every patient calling `ensure_fresh_assessment()`,
and `backend/app/engine/pipeline.py:compute_input_hash()` includes `date.today()` in the hash payload.
Consequence: the first worklist request of each calendar day recomputes the full engine for every
patient **and** regenerates every LLM narrative, synchronously, inside one HTTP request. At 10 demo
patients this is survivable; at 200 it exceeds a Lambda timeout. This one is confirmed and blocking.

## C4. General caution on agent-sourced numbers

The corpus is unusually well-sourced (most findings carry a PMID/DOI/URL), and each clinical and
data-source domain went through an adversarial verification pass. But the verification agents shared
the same tools and failure modes as the researchers. Before any number in this corpus goes into a
regulatory filing, a customer contract, a pitch deck, or a clinical threshold that gates a patient
alert, re-verify it against the primary source. Treat the corpus as a very good research memo, not as
a citation of record.
