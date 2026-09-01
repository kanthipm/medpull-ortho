# Retrieval-augmented generation for MedPull Recovery Copilot: whether RAG is warranted, over which corpus (patient record vs. clinical knowledge vs. roster), and how to build it

## Summary

RAG is not warranted for MedPull now, and for two of the three candidate corpora it is arguably never the right tool. (a) A patient's longitudinal record at RTM scale is a few tens of thousands of tokens of already-structured data; SQL over the existing store plus direct-context stuffing beats embeddings on correctness, auditability, and PHI safety, and Anthropic's own contextual-retrieval guidance says corpora under ~200k tokens should skip retrieval entirely. (c) Roster queries ("who reported fever this week") demand exhaustive recall over exact temporal/structured predicates — vector top-k retrieval can silently drop a febrile patient, which in a clinical product is a safety regression versus the current retrieve-then-verify-then-compose SQL pipeline; the right upgrade is deterministic symptom/red-flag tagging at check-in ingest, not embeddings. (b) Clinical knowledge is the only corpus where retrieval is eventually justified, but AAOS explicitly prohibits reproduction of its guideline content without written permission, so the ingestible corpus is the practice's own post-op protocols and patient-education material — which today fits in a cached prompt. The concrete trigger to build retrieval is the practice protocol library exceeding roughly 200k tokens or multi-practice onboarding; at that point the right build is pgvector inside the app's Postgres (hybrid tsvector BM25-style + dense with reciprocal rank fusion, contextual chunk headers, and a reranker), not a separate vector database — dedicated stores like OpenSearch Serverless cost ~$175–350/month minimum against a corpus worth a few dollars of embeddings. Before any of that, build a 50–100-question gold evaluation set and RAGAS-style faithfulness/context-precision harness, because the guardrail architecture (forced citation to chunk IDs, abstention on weak retrieval, hard per-patient partition enforcement) matters more than retrieval quality in this product.

## Findings

### Anthropic's own guidance: corpora under ~200k tokens should not use RAG at all
*[strong]*

Anthropic's contextual-retrieval engineering post states that if the knowledge base is smaller than 200,000 tokens (~500 pages) you should include it directly in the prompt with prompt caching rather than build retrieval. A single orthopedic practice's post-op protocol + patient-education library, and certainly any single patient's check-in history, sits well under this line. This is the single most load-bearing fact for the verdict.

> https://www.anthropic.com/news/contextual-retrieval

### Contextual retrieval + hybrid + rerank benchmark numbers (if/when retrieval is built)
*[strong]*

Anthropic reports top-20-chunk retrieval failure rate dropping from 5.7% baseline to 3.7% with contextual embeddings (-35%), 2.9% with contextual embeddings + contextual BM25 (-49%), and 1.9% with reranking added (-67%). One-time contextualization cost with prompt caching: $1.02 per million document tokens (800-token chunks + 100-token generated context). Retrieving 20 chunks outperformed 5 or 10. Voyage and Gemini were the strongest embedding providers in their tests. This is the recipe to copy when corpus (b) eventually crosses the threshold.

> https://www.anthropic.com/news/contextual-retrieval

### AAOS guideline text is copyrighted and non-redistributable without written permission
*[strong]*

OrthoGuidelines (AAOS's official CPG portal) states: 'This website and its contents may not be reproduced in whole or in part without written permission.' Guidelines are viewable free of charge, but ingesting AAOS CPG text into a commercial product's retrieval corpus requires a license from AAOS (Rosemont, IL). Freely usable alternatives: the practice's own protocols (practice-owned copyright), CMS/FDA regulatory text (public domain as US government works), FDA drug labels via openFDA/DailyMed (public domain), and CDC patient education. Encode AAOS recommendations as your own structured rule tables (facts/ideas are not copyrightable; verbatim text is) with citations pointing users to orthoguidelines.org rather than reproducing text.

> https://www.orthoguidelines.org/

### Per-patient longitudinal record: structured SQL dominates vector retrieval at this corpus size
*[strong]*

An RTM patient generates on the order of 90–180 check-ins over an episode; at ~100–300 tokens each plus notes and summaries, a full patient corpus is typically 20k–80k tokens — it fits whole in a Groq llama-3.3-70b 128k context, and the analytics bundle already summarizes it deterministically. Embedding search adds a lossy, non-auditable layer on top of data that is already typed (dates, pain scores, ROM, adherence, reason codes). Semantic search adds genuine value only for one narrow case: free-text transcript passages ('patient mentioned clicking sensation weeks ago') — and SQLite FTS5 / Postgres tsvector keyword search covers most of that without embeddings.

> Anthropic contextual retrieval post (200k-token threshold); corpus-size arithmetic from RTM cadence (CMS RTM codes 98977/98980 imply 16+ monitoring days/30-day period)

### Roster queries: vector retrieval is a safety downgrade versus the current retrieve-verify-compose pipeline
*[strong]*

Queries like 'who reported fever this week' are exhaustive-recall queries over exact predicates (symptom mention x time window x roster membership). Top-k dense retrieval provides no recall guarantee — a patient whose fever mention embeds atypically ('felt hot and shivery last night') can silently fall out of the candidate set, and a missed febrile post-op patient is a missed early-infection signal. The current SQL-retrieve → per-patient-verify → compose design is architecturally correct. The right investment is moving symptom detection earlier: run a small extraction pass (LLM or rule-based) at check-in ingest that writes typed symptom/red-flag rows (fever, wound drainage, calf pain, numbness, falls) with confidence and source-span offsets, so roster queries become pure indexed SQL.

> Architectural reasoning from top-k retrieval semantics; consistent with Anthropic guidance that retrieval is for corpora too large for context, not for exhaustive structured queries

### Naive fixed-size chunking fails specifically on clinical protocol documents
*[strong]*

Post-op protocols are phase-structured (e.g., 'Phase II, weeks 2–6: flexion to 90°, WBAT, discontinue CPM') with week-by-week tables, ROM milestone grids, and red-flag lists. Fixed 512-token windows split table rows from headers and milestones from their phase/procedure context, so a retrieved chunk can pair week-6 ROM targets with the wrong procedure or phase — a clinically dangerous confusion. Correct approach: structure-aware chunking with one chunk per protocol phase or per red-flag section, tables kept atomic, and every chunk prefixed with a generated context header (procedure, protocol name, phase, week range) per Anthropic's contextual-retrieval method — which is precisely what drove their 35–49% failure-rate reductions.

> https://www.anthropic.com/news/contextual-retrieval; document-structure analysis of standard orthopedic rehab protocols

### Embedding model landscape and pricing (July 2026)
*[strong]*

Voyage (now MongoDB-owned): voyage-4-large $0.12/M tokens, voyage-4 $0.06/M, voyage-4-lite $0.02/M, with 200M free tokens — at MedPull's corpus size the entire embedding workload is effectively free forever. Older voyage-3-large ($0.18/M) claimed ~9.7% average retrieval advantage over OpenAI text-embedding-3-large at launch (Jan 2025). OpenAI text-embedding-3-large $0.13/M (MTEB avg ~64.6), -3-small $0.02/M. Cohere Embed v4 ~$0.12/M (per-token pricing now partly obscured behind 'Model Vault' hourly tiers of $4–5/hr). BGE-M3 (BAAI, MIT license) is free, self-hostable, and does dense+sparse+multi-vector in one model. Medical-domain models: MedCPT (NCBI, PubMedBERT-based, 768-dim, trained on 255M PubMed search-log pairs) is built for biomedical *literature* retrieval, not clinical notes or rehab protocols — wrong domain match for MedPull; MedEmbed (2024 BGE fine-tune) has thin independent evaluation. Recommendation when needed: voyage-4-lite or text-embedding-3-small; domain medical embeddings are not indicated.

> https://docs.voyageai.com/docs/pricing; https://github.com/ncbi/MedCPT; https://cohere.com/pricing

### Reranking: cheap, high-lift, and the easiest quality win when retrieval exists
*[moderate]*

In Anthropic's benchmark, adding a reranker on top of contextual hybrid retrieval cut failure rate from 2.9% to 1.9% (a further ~34% relative reduction). Voyage rerank-2.5 is $0.05/M tokens and rerank-2.5-lite $0.02/M with 200M free tokens; Cohere Rerank 3.5 (Dec 2024) prices per search unit (1 query x up to 100 docs), historically ~$2.00/1K searches. At MedPull query volumes (hundreds of clinician queries/day even at 10,000 patients), reranking cost is negligible. Cross-encoder rerankers also enable a principled abstention signal: if the top reranked score is below a calibrated threshold, decline to answer rather than compose from weak context.

> https://www.anthropic.com/news/contextual-retrieval; https://docs.voyageai.com/docs/pricing; https://cohere.com/blog/rerank-3pt5 (headline only; per-search pricing from prior Cohere pricing pages)

### Vector store economics: dedicated infrastructure is wildly disproportionate at MedPull scale
*[strong]*

Corpus math: 100 patients ≈ 5M tokens of transcripts ≈ 10k chunks ≈ tens of MB of vectors; 10,000 patients ≈ a few GB — trivial for any option. Amazon OpenSearch Serverless classic collections bill a 2-OCU minimum ≈ $350/month (dev-test 1 OCU ≈ $175/month) at $0.24/OCU-hour — hundreds of dollars monthly before storing a single useful vector (a NextGen scale-to-zero tier now exists but is the exception, not the default Bedrock KB path). Pinecone Standard has a $50/month minimum; Qdrant Cloud free tier is 1GB then ~$25+/month. Bedrock Knowledge Bases itself is free but you pay the backing store; its new S3 Vectors backend (claims 'up to 90%' cost reduction vs. dedicated vector DBs, 100ms+ warm latency) is the only AWS-native option that is cost-rational here. But all of these lose to pgvector 0.8.6 (HNSW with m/ef_construction tuning, iterative_scan for filtered queries, halfvec, binary quantization) running inside the Postgres MedPull already plans to adopt: $0 marginal cost, one backup/HIPAA-BAA surface, and SQL joins between vectors and the clinical schema.

> https://aws.amazon.com/opensearch-service/pricing/; https://aws.amazon.com/s3/features/vectors/; https://github.com/pgvector/pgvector

### sqlite-vec fits the current SQLite stack but is explicitly pre-v1
*[strong]*

sqlite-vec (Mozilla Builders-sponsored, pure C, runs in Lambda) supports KNN with metadata/partition-key columns and int8 quantization, with IVF/DiskANN ANN work in the codebase, but the README states 'sqlite-vec is a pre-v1, so expect breaking changes.' It is acceptable for an experiment on the current SQLite deployment, but pinning a clinical product's retrieval layer to a pre-1.0 extension is not; the Postgres migration with pgvector is the stable path.

> https://github.com/asg017/sqlite-vec

### Hybrid BM25 + dense with reciprocal rank fusion is the correct retrieval shape for clinical text
*[strong]*

Clinical queries are dense with exact-match tokens that embeddings blur: drug names (Eliquis vs. Xarelto), CPT/procedure codes, laterality (left vs. right TKA), and numeric thresholds (fever >101.5°F). BM25/full-text catches these exactly; dense embeddings catch paraphrase ('leg feels hot and tight' → DVT red-flag section). RRF (score = sum of 1/(k+rank), k=60) fuses the two without score calibration and is natively available in Postgres via tsvector + pgvector in one SQL statement. Anthropic's data shows the hybrid (contextual BM25 + contextual embeddings) beating embeddings alone by 14 points of relative failure reduction (49% vs. 35%). Postgres full-text search alone is a legitimate v1: for a small protocol corpus with forced citations, tsvector + ts_rank may hit acceptable recall with zero new infrastructure.

> https://www.anthropic.com/news/contextual-retrieval; https://github.com/pgvector/pgvector (iterative_scan for filtered hybrid queries)

### RAG evaluation: RAGAS metrics plus a small TREC-style graded gold set
*[strong]*

RAGAS provides faithfulness (is the response grounded in retrieved context), response relevancy, context precision (fraction of retrieved chunks that are relevant), context recall (fraction of needed evidence retrieved), and noise sensitivity (robustness to irrelevant/conflicting context) — mostly LLM-judged. For MedPull: build a 50–100-question gold set from real clinician questions (protocol lookups, red-flag checks, roster queries), grade relevance TREC-style on a 0–3 scale per (query, chunk) pair judged by a clinician, and track nDCG@10 and recall@20 for retrieval plus RAGAS faithfulness for generation. Pin it in CI exactly like the existing golden-tier tests. Crucially, this harness is worth building *now* — it also evaluates the existing deterministic ask-the-roster pipeline and any future retrieval against the same yardstick.

> https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/

### Cross-patient PHI contamination is a reportable breach — controls must be structural, not prompt-level
*[strong]*

Under HIPAA's Breach Notification Rule (45 CFR §§164.400–414), impermissible disclosure of one patient's PHI in another patient's (or wrong clinician's) output is presumptively a reportable breach. Required architecture if patient text is ever embedded: (1) patient_id as a mandatory, database-enforced pre-filter — Postgres row-level security policies on the chunks table so the query role physically cannot see other patients' rows (pgvector supports filtered HNSW scans via iterative_scan; never post-filter after top-k); (2) no shared cross-patient semantic index for patient-facing features — cross-patient search exists only in the clinician roster path, which stays SQL; (3) chunk IDs carry patient_id and the composer validates every cited chunk against the request's patient_id before rendering, failing closed to deterministic text (mirroring the existing guardrail-fallback pattern); (4) embedding vectors of PHI are themselves PHI (inversion attacks reconstruct text from embeddings) — any embedding API call on transcripts requires a BAA, which AWS Bedrock offers as HIPAA-eligible; Voyage/OpenAI require enterprise agreements; this alone favors self-hosted BGE-M3 or Bedrock-hosted embedding (Titan/Cohere) for patient text.

> 45 CFR §§164.400–414 (HIPAA Breach Notification Rule); https://github.com/pgvector/pgvector; embedding-inversion literature (Morris et al., 'Text Embeddings Reveal (Almost) As Much As Text', EMNLP 2023)

### Citation grounding and abstention: the forced-attribution contract extends MedPull's existing guardrail design
*[moderate]*

When retrieval ships for corpus (b), the JSON contract should require every clinical claim to carry a chunk_id citation resolvable to a protocol section shown in the UI (title + phase + practice document version); the validator rejects responses citing nonexistent IDs or containing uncited clinical assertions, falling back to deterministic text — the exact pattern MedPull already uses for banned-language violations. Abstention: if fewer than N chunks clear a reranker score threshold (calibrate on the gold set), return 'no protocol guidance found for this question' rather than composing. This is materially safer than typical RAG because the fallback path already exists and is tested.

> Design synthesis from Anthropic contextual-retrieval reranking guidance and MedPull's existing contract-validation/fallback architecture

### Query rewriting: low priority, one narrow use
*[moderate]*

Query rewriting (LLM reformulates the user query before retrieval, e.g. HyDE or multi-query expansion) adds latency and an extra failure mode; measured gains are corpus-dependent and largely subsumed by contextual retrieval + reranking in Anthropic's stack. The one narrow fit for MedPull: expanding clinician shorthand ('POD3 TKA fever w/u') into full terms before BM25 — a deterministic abbreviation dictionary (POD→post-op day, TKA→total knee arthroplasty) gets most of that value with zero LLM calls, consistent with the project's Groq-then-deterministic cost posture.

> https://www.anthropic.com/news/contextual-retrieval (positions contextual retrieval as superseding several query-side techniques for their benchmark)


## Implications for backend

- The planned SQLite → Postgres migration becomes the retrieval decision point: choosing Postgres with pgvector 0.8.x + tsvector preserves a zero-cost upgrade path to hybrid retrieval inside the existing HIPAA/BAA boundary, so no separate vector-store procurement, backup, or security review is ever needed at 100 or 10,000 patients.
- Add a symptom_events table (patient_id, checkin_id, symptom_code, span_offsets, confidence, detected_at) populated at ingest; index on (symptom_code, detected_at) — this converts ask-the-roster's retrieve stage to a single indexed query and creates the substrate for future predictive-risk features.
- Protocol chunks need a first-class schema now even without vectors: (practice_id, document_id, version, procedure, phase, week_range, section_type, text, context_header) — versioning matters because citing a superseded protocol revision in an RTM note is a clinical-documentation defect; the existing input-hash output cache must include protocol document version in the hash.
- If patient text is ever embedded, enforce isolation in the database, not the application: Postgres row-level security keyed on patient_id/practice_id with pgvector iterative_scan pre-filtering; the LLM composer must re-validate every cited chunk's patient_id against the request and fail closed to the deterministic renderer, reusing the existing guardrail-fallback code path.
- Groq remains the generation layer, but any embedding of PHI must go through a BAA-covered path (AWS Bedrock is HIPAA-eligible; the Lambda deployment on account 099660945689 makes Bedrock-hosted embeddings the natural fit) — verify Groq BAA status before conversational SMS check-ins ship, since those transcripts are PHI at creation.
- The gold-set + RAGAS harness should be built against the CURRENT deterministic pipeline first — it doubles as regression protection for ask-the-roster and the guardrail fallbacks, and pins the baseline any future retrieval must beat before it is allowed to ship.

## Recommendation
**Do not build RAG now. Never build vector retrieval for the per-patient record (corpus a) or roster queries (corpus c) — keep and harden the SQL/deterministic paths. Corpus (b), the practice's own protocol and patient-education library, is the only future RAG candidate: serve it today via direct context with prompt caching and Postgres/SQLite full-text search, and graduate to pgvector hybrid retrieval inside the app database only when the protocol library exceeds ~200k tokens or multi-practice onboarding makes per-practice protocol grounding necessary.**

Every corpus fails the size test that Anthropic itself publishes as the threshold for RAG (~200k tokens): a patient's full record fits in one cached prompt, the roster is a structured table, and a practice's protocol library is a few hundred pages. Vector retrieval would replace exhaustive, auditable SQL with probabilistic top-k in exactly the queries where a miss (an undetected fever report) is a clinical safety failure, and would create a new PHI surface (embeddings of transcripts are PHI, requiring BAAs and breach-grade tenant isolation) with no compensating quality gain. Meanwhile the licensing reality removes the most tempting corpus: AAOS explicitly forbids reproducing guideline content without written permission, so the ingestible clinical-knowledge corpus is practice-owned material that is currently small. The genuinely valuable near-term work that RAG energy should be redirected to: structured symptom/red-flag extraction at check-in ingest (making roster queries pure SQL), a graded gold-set evaluation harness (which de-risks any future retrieval and improves today's ask-the-roster feature), and protocol-grounded responses via cached direct context with forced citations.

**Do NOT:**
- Do not ingest AAOS clinical practice guideline text into any corpus without a written license — OrthoGuidelines states content 'may not be reproduced in whole or in part without written permission'; encode recommendations as your own rule tables and link out instead.
- Do not build a shared cross-patient vector index over check-in transcripts — top-k retrieval has no recall guarantee for 'who reported X' queries, and a cross-patient leak from a mis-filtered index is a reportable HIPAA breach (45 CFR §§164.400–414).
- Do not adopt Amazon OpenSearch Serverless / Bedrock Knowledge Bases' default stack — the ~$175–350/month OCU floor is indefensible for a corpus whose full embedding cost is under $1; if AWS-native is ever required, S3 Vectors is the only cost-rational backend.
- Do not send patient transcript text to any embedding API without a signed BAA — embedding vectors are PHI (inversion attacks reconstruct source text); Bedrock-hosted or self-hosted (BGE-M3) embedding only.
- Do not pin production retrieval to sqlite-vec — it is self-described pre-v1 with expected breaking changes; it is fine for a spike, not for a clinical product.
- Do not buy a medical-domain embedding model — MedCPT targets PubMed literature retrieval, not rehab protocols or patient messages; general models (voyage-4-lite, text-embedding-3-small) with contextual chunk headers will outperform it on this corpus.
- Do not add LLM query rewriting — a deterministic clinician-abbreviation dictionary captures the value at zero cost and fits the Groq-then-deterministic posture.

**Sequencing:**
- 1. (1–2 weeks) Structured symptom/red-flag extraction at check-in ingest: typed rows (fever, drainage, calf pain, numbness, fall) with source-span offsets and confidence, written alongside the analytics bundle; roster queries become indexed SQL and the existing retrieve-verify-compose gets faster and exhaustive.
- 2. (1 week) Gold evaluation set: 50–100 real clinician questions across protocol lookup, red-flag checks, and roster queries; clinician-graded 0–3 relevance TREC-style; wire nDCG@10 / recall@20 plus RAGAS faithfulness and context-precision into CI next to the golden-tier tests.
- 3. (1–2 weeks) Protocol grounding v1 without retrieval: ingest the practice's own protocols as structure-aware chunks (one per phase/red-flag section, tables atomic, generated context headers) into a plain table; serve the relevant procedure's full protocol in the prompt with caching; JSON contract requires chunk_id citations, validator fails closed to deterministic text.
- 4. (At Postgres migration) Add tsvector full-text search over protocol chunks and transcripts (free, no new infra); evaluate against the gold set — this may be terminal.
- 5. (Only on trigger: protocol corpus >~200k tokens or multi-practice) Add pgvector 0.8.x HNSW + hybrid RRF + voyage rerank-2.5-lite or Cohere Rerank 3.5, with abstention thresholds calibrated on the gold set; embeddings via Bedrock (BAA) or self-hosted BGE-M3 for anything touching PHI.
- 6. (Deferred indefinitely) Any per-patient semantic search — revisit only if transcripts grow beyond context limits AND FTS provably misses clinician queries in the gold set.

## Open questions

- Does Groq offer a BAA / HIPAA-eligible tier suitable for the roadmap's conversational SMS check-ins? If not, the generation layer for transcript-bearing prompts may need to move to Bedrock (e.g., Claude on Bedrock) — a larger architectural question than RAG itself.
- Will AAOS license CPG text for commercial clinical-decision-support ingestion, and at what cost? A written inquiry to AAOS permissions is cheap and would unlock corpus (b)'s highest-value content; until answered, assume link-out-only.
- What is the actual token size and heterogeneity of a typical customer practice's protocol library? If multi-surgeon practices carry 20+ procedure protocols x revisions, the 200k-token threshold could arrive sooner than expected — measure during the next practice onboarding.
- Is Amazon S3 Vectors GA with published pricing and Bedrock KB support in all target regions (the page fetched did not state GA status)? Relevant only if an AWS-managed path is later preferred over pgvector.
- Cohere appears to be shifting from per-token/per-search pricing to hourly 'Model Vault' tiers ($4–10/hr) — confirm whether classic pay-as-you-go Embed/Rerank pricing remains available before depending on it; Voyage's 200M-free-token tier currently makes this moot.
- For the eventual conversational check-in feature: does adaptive questioning need retrieval at all, or is it better served by the deterministic analytics bundle + recovery-stage state machine in the prompt? Preliminary answer is the latter, but this should be decided with the gold set in hand.