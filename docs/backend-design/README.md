# Recovery Copilot — backend research & design corpus

Produced 2026-07-31 by a 57-agent research fan-out (56 completed, 1 lost) across five
workflows: clinical domain, data sources, statistical methods, AI architecture/regulatory,
and a synthesis round with adversarial review.

## Read in this order

| File | What it is |
| --- | --- |
| `00-CORRECTIONS-READ-FIRST.md` | **Start here.** Claims from the corpus that I verified independently and found wrong or unverifiable — including one load-bearing FDA claim. |
| `01-current-engine-gaps.md` | What I found reading the current `backend/app/` source, independent of the literature. Eight defects, one critical. |
| `07-chief-engineer-build-plan.md` | **The reconciled view.** Adjudicates 30+ contradictions between the design sections, then gives an ordered, dependency-correct 90-day plan (119 engineer-days) and the 17 decisions only the founder can make. |
| `08-skeptical-review.md` | The strongest attack on the whole plan. Names the most likely reason it fails and the $3k / 2-week experiment that would surface it. |
| `02-data-layer.md` | Ingestion, the Observation store, the step-count crisis, wearables, EHR/labs. |
| `03-statistical-engine.md` | Baselines, deviation detection, composite, trajectory, alerting, serving contract. |
| `04-clinical-content.md` | What orthopedic surgeons measure and act on; complication surveillance; per-procedure clocks; PROMs; the commercial frame. |
| `05-ai-runtime-compliance.md` | Train/fine-tune, RAG, MCP, LLM quality gates, FDA position, runtime architecture, cost. |
| `06-completeness-review.md` | What everyone missed — PT data stream, disengagement as signal, liability of silence, business failure modes. |
| `research/` | The raw corpus: 31 research memos + 14 adversarial verification passes + 4 critiques, with citations. |

## The five things that matter most

1. **The engine is measuring the wrong thing.** Patient-reported wound drainage carries
   88% sensitivity / 88% specificity for acute PJI in week 2 and NPV >98% when absent.
   Wearable vitals give **7–14 hours** of lead time, not days. The product's core signal
   should be the check-in, with physiology as a corroborator.
2. **Wrist step counting collapses in exactly our population** — 31–36% undercount with a
   walker. Weeks 0–3 of step data measure gait-aid use, not recovery. Assistive-device
   capture is a hard dependency of the entire functional layer.
3. **The Apple cohort silently loses 45% of the composite index** (`01-current-engine-gaps.md`
   G1). The seed data masks it; real Apple Watch data would expose it immediately.
4. **Train nothing, RAG nothing, MCP nothing** — with specific trigger conditions for
   revisiting each. See `05-ai-runtime-compliance.md` §4.1–4.3.
5. **`GET /worklist` recomputes every patient and regenerates every LLM narrative
   synchronously on the first request of each day.** Verified. It will time out in
   production well before 200 patients.

## Provenance and how much to trust this

Every clinical and data-source memo went through an adversarial verification pass against
primary sources, and those corrections are in `research/*VERIFICATIONS.md`. The synthesis
round was attacked by two independent judges who checked claims against the actual codebase
and found several wrong (documented in `07-chief-engineer-build-plan.md` Part 1).

That said: verification agents share the failure modes of research agents. **Re-verify any
number against its primary source before it enters a regulatory filing, a customer contract,
a pitch deck, or a threshold that gates a patient alert.** At least one confidently-stated
regulatory fact did not survive my own check — see `00-CORRECTIONS-READ-FIRST.md`.
