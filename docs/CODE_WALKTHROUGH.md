# FinSight — Code Walkthrough (for a technical interviewer)

A sequential reading order for explaining this codebase to a software engineer.
Read the files in the order below; each builds on the previous. File paths are
clickable. Line counts are rough (as of this writing) to signal weight.

**The one-sentence architecture:** a query flows through a 6-node LangGraph
pipeline — understand → route → retrieve (hybrid) → rerank → detect conflicts →
generate (cited) — served by FastAPI, backed by Qdrant Cloud (vectors) and Claude
(reasoning), with the whole thing evaluated by an offline ablation + faithfulness
suite.

The mental model to hold while reading: **there are three subsystems** —
(1) *ingestion/indexing* (offline, builds the search index),
(2) *retrieval/serving* (online, answers a query),
(3) *evaluation* (offline, measures quality). Read them in that order.

---

## Layer 0 — Foundations (read first; everything imports these)

**1. [src/utils/config.py](../src/utils/config.py)** (~130 lines) — *start here.*
Single pydantic-settings `Settings` class, instantiated once as `settings`. Every
other file imports it. Shows the whole system's knobs at a glance: model IDs
(`claude-sonnet-4-6`, `claude-haiku-4-5`, `voyage-finance-2`, `rerank-v3.5`),
`embedding_backend`, `retrieval_mode`, `reranker_backend`, cost caps, paths.
**Interview point:** required secrets are `Field(...)` → the app fails fast at
import if a key is missing (this is also why CI passes dummy env vars).

**2. [src/utils/logging.py](../src/utils/logging.py)** (~40 lines) — trivial;
one `get_logger(__name__)` helper. Skim.

---

## Layer 1 — Ingestion & Indexing (offline: raw data → searchable index)

Read this layer to understand *how the search index is built* before seeing how
it's queried.

**3. [src/ingestion/schema.py](../src/ingestion/schema.py)** (~174 lines) — the
DuckDB data model. 5 tables: `documents` (one row per source doc), `chunks`
(chunked text + metadata — the retrieval unit), `fundamentals` + `prices` (SEC/
OHLCV, ingested but not yet on retrieval paths), `ingestion_runs` (run audit).
**Interview point:** DuckDB is the columnar system-of-record; Qdrant holds only
vectors + a payload copy of the text. Two stores, clear separation of concerns.

**4. [src/ingestion/motley_fool_loader.py](../src/ingestion/motley_fool_loader.py)**
(~200 lines) — loads the raw earnings-call transcripts (a Kaggle pickle) into the
`documents` table, filtered to the 76-ticker universe, with fiscal-quarter parsing
and an `ingestion_runs` audit record. `ohlcv_loader.py` and `sec_filing_parser.py`
are the analogous loaders for the other sources — skim one, note the pattern.

**5. [src/indexing/chunker.py](../src/indexing/chunker.py)** (~150 lines) — three
chunking strategies (`fixed_400`, `sentence`, `paragraph`) behind one
`chunk_text(text, strategy, max_tokens, overlap)` function. Pure, no I/O →
trivially unit-testable. **Interview point:** chunking strategy is a *per-corpus*
choice, not global (see next file).

**6. [src/indexing/embedder.py](../src/indexing/embedder.py)** (~150 lines) — the
embedding abstraction. `get_embedder()` returns a `VoyageEmbedder` (API, primary)
or `BgeM3Embedder` (local, fallback) based on config — both 1024-dim so they're
drop-in. Also `get_sparse_embedder()` for BM25 (fastembed) used by hybrid search.
**Interview points:** (a) the Protocol + factory pattern makes the backend
swappable; (b) `VoyageEmbedder` distinguishes `input_type="document"` vs
`"query"`; (c) `_with_retry` handles rate-limit/timeout with backoff.

**7. [src/indexing/qdrant_client.py](../src/indexing/qdrant_client.py)** (~110
lines) — thin Qdrant wrapper: `get_client()`, `ensure_collection()` (defines the
named-vector schema: a `dense` 1024-dim vector + a `bm25` sparse vector + payload
indexes on ticker/date/etc.). This is where the hybrid-search index shape is
declared.

**8. [src/indexing/ingest_vectors.py](../src/indexing/ingest_vectors.py)** (~294
lines) — **the ingestion pipeline that ties Layer 1 together.** For each document:
pick a chunking strategy *by doc_type* (transcripts→paragraph, MD&A→sentence,
8-K→fixed — the per-corpus tuning), chunk, embed in batches, write chunks to
DuckDB, upsert dense vectors to Qdrant. **Interview points:** deterministic
UUID5 point IDs (idempotent re-ingest), batched embedding (Voyage 128-input cap),
`ingestion_runs` audit. This is the "build the index" entry point.

> At this point the index exists: 15,023 chunks in DuckDB + Qdrant, each with a
> voyage-finance-2 dense vector and a BM25 sparse vector.

---

## Layer 2 — Retrieval & Serving (online: query → cited answer)

This is the heart. Read in dependency order: retriever → reranker → conflict
detector → generator → the graph that orchestrates them → the API that serves it.

**9. [src/retrieval/retriever.py](../src/retrieval/retriever.py)** (~149 lines) —
stage-1 retrieval. `Retriever.search(query, mode)` runs either `dense` (Week-1
baseline, kept for the ablation) or `hybrid` (default). **Interview centerpiece:**
`_hybrid_query` issues ONE Qdrant call with two `Prefetch` legs (dense + BM25
sparse) fused server-side by `FusionQuery(Fusion.RRF)` — native reciprocal-rank
fusion, no client-side merging. Then it hydrates full chunk text (from the Qdrant
payload on deploy, or DuckDB locally — `use_duckdb_hydration` config).

**10. [src/retrieval/reranker.py](../src/retrieval/reranker.py)** (~99 lines) —
stage-2 rerank. `Reranker.rerank(query, chunks, k)` re-scores the candidate pool
with Cohere `rerank-v3.5` (a cross-encoder), returns top-k. **Interview point:
the graceful-degradation chain** — Cohere error → local ms-marco cross-encoder →
raw retrieval order. Never fails the query.

**11. [src/insight/conflict_detector.py](../src/insight/conflict_detector.py)**
(~313 lines) — **the differentiator.** Two-step engine: (1) one Claude call
extracts structured `NumericClaim`s (metric, subject, value, period, is_guidance)
from the evidence; (2) pairwise-compare with per-metric thresholds to flag
contradictions. **The interview story lives in `_compare`'s precision gates** —
each gate kills a false-positive class found by inspecting real output:
different-chunk (not guidance ranges), comparable-period (not quarter-vs-year),
same-subject (not Products-vs-Services), different-date (real cross-call). This
is the "how I made it precise, not just built it" narrative.

**12. [src/generation/generator.py](../src/generation/generator.py)** (~206
lines) — answer generation. Claude Sonnet, `generate()` (batch) and
`generate_stream()` (SSE token streaming). **Interview point:** citations are
**inline `[N]` markers parsed post-hoc** into structured `Citation` objects — a
deliberate choice over forced tool-use, because forced-tool-use buffers the whole
JSON and kills streaming (first token 11s→1.3s). Also: pinned to `api.anthropic.com`
+ certifi to bypass a corporate proxy; abstains ("INSUFFICIENT EVIDENCE") when
ungrounded.

**13. [src/retrieval/graph_state.py](../src/retrieval/graph_state.py)** (~55
lines) — the `FinSightState` TypedDict that threads through the pipeline. Read it
as the "data contract": what each node reads and writes. Small, worth reading in
full.

**14. [src/retrieval/nodes.py](../src/retrieval/nodes.py)** (~322 lines) — **the 6
node functions.** `query_understanding` (Haiku: rewrite + ticker + temporal ref),
`router` (Haiku: 3-path classify), `retrieve` (hybrid), `rerank` (+ query-relative
temporal boost + staleness flag), `detect_conflicts` (gated on comparison intent),
`generate` (+ cost + failure-mode logging). **Interview points:** the two Haiku
nodes vs Sonnet generation = the *cost-routing story*; every node degrades
gracefully on error; conflict detection is intent-gated so its ~14s cost is only
paid when relevant.

**15. [src/retrieval/graph.py](../src/retrieval/graph.py)** (~73 lines) — **the
orchestration.** Compiles the LangGraph `StateGraph`: wires the 6 nodes as a linear
DAG (START → understand → route → retrieve → rerank → detect_conflicts →
generate → END), enables LangSmith tracing. `run_pipeline(query, top_k)` is the
one function the API calls. Short — read it to see the whole flow in one place.

**16. [api/main.py](../api/main.py)** (~298 lines) — **the serving layer.**
FastAPI app: `/health` (dependency check), `/query` (full pipeline), `/query/stream`
(SSE), `/recommend/{ticker}` (related tickers), `/feedback`. **Interview points:**
lazy singletons (don't load models at import), a `lifespan` warmup (pre-loads to
avoid cold-start on the first real query), pydantic request/response schemas
throughout.

**17. [src/recommendations/related_tickers.py](../src/recommendations/related_tickers.py)**
(~112 lines) — the second ML product on shared infra. Builds a per-ticker centroid
(mean of its chunk vectors), cosine-NN between centroids = "related companies." No
LLM. **Interview point:** "retrieval and recommendation are the same nearest-
neighbor problem over one embedding space."

**18. [ui/streamlit_app.py](../ui/streamlit_app.py)** (~208 lines) — thin client.
Streams tokens from `/query/stream`, renders the answer, citations, conflicts,
routing path, staleness badge, and metrics. HTTP-only — no business logic.

---

## Layer 3 — Evaluation (offline: measure quality)

Read last. This is what turns "I built a RAG system" into "I measured it."

**19. [src/evaluation/golden_set.py](../src/evaluation/golden_set.py)** (~181
lines) — builds the 50-query golden set: 40 corpus-grounded (generated *from* real
chunks so a relevant chunk provably exists) + 5 adversarial + 5 abstention.

**20. [src/evaluation/ablation.py](../src/evaluation/ablation.py)** (~211 lines) —
**the headline eval.** Compares dense vs hybrid vs hybrid+rerank on the golden set;
relevance labels via **LLM pooling** (standard IR technique); metrics Recall@5 /
MRR / NDCG@10. Produces the "+27.4% NDCG" result. Doubles as the reranker ablation.

**21. [src/evaluation/ragas_runner.py](../src/evaluation/ragas_runner.py)** (~135
lines) — RAGAS faithfulness (the anti-hallucination gate, 0.806) with Claude judge
+ Voyage embeddings. **[faithfulness.py](../src/evaluation/faithfulness.py)** is a
framework-free alternative judge (kept as a lighter option).

**22. [src/evaluation/chunking_ablation.py](../src/evaluation/chunking_ablation.py)**
+ **[llm_compare.py](../src/evaluation/llm_compare.py)** — the chunking-strategy
ablation and a model-agnostic Claude-vs-X harness. Skim.

**23. [src/utils/cost_tracker.py](../src/utils/cost_tracker.py)** +
**[failure_tracker.py](../src/utils/failure_tracker.py)** (~75 lines each) —
per-query cost estimation and 5-mode failure classification, logged to JSONL. The
production-observability signals.

---

## Layer 4 — Tests & scripts (supporting cast)

- **[tests/test_unit.py](../tests/test_unit.py)** + **[test_week4.py](../tests/test_week4.py)** —
  23 no-API unit tests: chunking, conflict precision gates, temporal boost,
  citation parsing, cost math, failure classification, the feedback endpoint. These
  are what CI runs.
- **[scripts/](../scripts/)** — operational tooling: `download_sec_edgar.py`,
  `add_sparse_vectors.py` (populate BM25 vectors), `push_to_cloud.py` (local→Qdrant
  Cloud), `reembed_chunks.py` (resumable re-embed), `check_serve_imports.py` (CI
  guard against serve/local dependency drift). Not part of the request path.

---

## The 5-minute version (if the interviewer is impatient)

Read just these six, in order, and you can explain the whole system:
1. [config.py](../src/utils/config.py) — the knobs
2. [ingest_vectors.py](../src/indexing/ingest_vectors.py) — how the index is built
3. [retriever.py](../src/retrieval/retriever.py) — hybrid retrieval (the RRF fusion)
4. [conflict_detector.py](../src/insight/conflict_detector.py) — the differentiator + precision gates
5. [graph.py](../src/retrieval/graph.py) — the 6-node orchestration
6. [ablation.py](../src/evaluation/ablation.py) — how it's measured (+27.4% NDCG)
