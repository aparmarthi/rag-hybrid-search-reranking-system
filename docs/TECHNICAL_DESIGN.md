# FinSight — Technical Design Document

**System:** FinSight — a production RAG system for investor-grade financial research.
**Status:** Weeks 1–4 complete + React frontend; live on Google Cloud Run (always on, DEC-019) + Qdrant Cloud; Render kept as a backup.
**Companion docs:** [architecture.md](architecture.md) (diagrams), [CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md)
(reading order), [decisions.md](decisions.md) (decision log DEC-001…023), [PRD.md](PRD.md) (product).

---

## 1. Problem & scope

Equity analysts spend hours cross-referencing three disconnected sources —
earnings-call transcripts (what management *said*), SEC filings (what they
*filed*), and market data (how the stock *moved*) — and have no systematic way to
surface when those sources disagree. FinSight answers natural-language questions
over this corpus with **cited, grounded answers**, and — the differentiator —
**detects and surfaces numeric contradictions** (e.g. guidance in one quarter vs
the actual in a later call) instead of silently averaging them.

**Current scope:** earnings-call transcripts — **15,023 chunks, 76 tickers,
2019–2023**. SEC filings and OHLCV are ingested into the store but not yet on the
live retrieval paths (see §9 Roadmap). The system is honest about this: queries
routed to the un-ingested paths abstain rather than fabricate.

**Non-goals:** real-time market data, trade execution, buy/sell advice (explicitly
guard-railed out).

---

## 2. High-level architecture

Three subsystems:

```
┌─ INGESTION (offline) ─────────────┐   ┌─ SERVING (online) ──────────────────────┐
│ raw sources → DuckDB documents    │   │ FastAPI → 6-node LangGraph pipeline      │
│   → chunk → embed → Qdrant + DuckDB│   │   understand→route→retrieve→rerank        │
└───────────────────────────────────┘   │   →detect_conflicts→generate → SSE        │
                                         └──────────────────────────────────────────┘
┌─ EVALUATION (offline) ────────────┐        backed by:  Qdrant Cloud (vectors)
│ golden set → ablations + RAGAS    │                     Claude (Sonnet+Haiku)
│   → Recall/NDCG/faithfulness       │                     Voyage (embeddings), Cohere (rerank)
└───────────────────────────────────┘
```

**Design principle throughout: graceful degradation + honesty.** Every external
dependency (Voyage, Cohere, Claude, Qdrant) has a fallback or a safe failure mode,
and the system abstains rather than hallucinates when it can't ground an answer.

---

## 3. Data model

Two stores, deliberately separated by role:

**DuckDB** (columnar system-of-record, `data/processed/finsight.duckdb`):

| Table | Purpose |
|---|---|
| `documents` | one row per source doc (transcript / filing), with metadata + raw text |
| `chunks` | chunked text units (the retrieval grain) + ticker/date/fiscal metadata |
| `fundamentals` | SEC XBRL numbers (ingested, not yet on a retrieval path) |
| `prices` | OHLCV daily bars (ingested, not yet on a retrieval path) |
| `ingestion_runs` | audit trail of every ingest run (status, row counts, errors) |

**Qdrant** (vector search, `finsight_chunks` collection):
- Named vectors per point: **`dense`** (1024-dim, voyage-finance-2) + **`bm25`**
  (sparse, for hybrid).
- Payload: `chunk_id`, `ticker`, `doc_type`, `section`, `date`, `fiscal_year/quarter`,
  and a copy of the chunk **text** (so the deployed app needs no DuckDB at serve time).
- Payload indexes on ticker/doc_type/section/date for fast filtering.

**Why two stores:** DuckDB is the durable, queryable source-of-truth (10–50× faster
than SQLite/Postgres for the columnar OHLCV/fundamentals workload); Qdrant does what
it's best at — approximate nearest-neighbor. Deterministic UUID5 point IDs
(`uuid5(chunk_id)`) keep the two in sync and make re-ingestion idempotent.

---

## 4. Ingestion & indexing pipeline (offline)

```
raw (Kaggle pkl / SEC HTML / OHLCV csv)
  → loader (src/ingestion/*)        → DuckDB.documents  (filtered to 76-ticker universe)
  → ingest_vectors.py:
       pick chunking strategy by doc_type
       → chunk_text()               → Chunk objects
       → embedder.embed_documents() → 1024-dim vectors (batched, ≤128/req for Voyage)
       → write DuckDB.chunks + upsert Qdrant (dense)
  → add_sparse_vectors.py           → add BM25 sparse vector to each point
  → push_to_cloud.py                → copy local Qdrant → Qdrant Cloud (full text in payload)
```

**Per-corpus chunking** (the key indexing decision): chunk strategy is chosen by
document type, not globally — transcripts→`paragraph` (preserves speaker turns),
MD&A→`sentence` (flowing narrative), 8-K→`fixed_400` (short/structured). All at
`max_tokens=600, overlap=80`. Structure-aware, not embedding-based semantic
chunking — the pragmatic choice for already-structured transcripts (DEC + the
Week-3 chunking ablation).

**Embeddings:** voyage-finance-2 (domain-tuned, API → no local model) primary;
bge-m3 (local, 1.3GB) fallback. Both 1024-dim → interchangeable collection shape,
but vectors from different models aren't comparable, so switching requires a full
re-embed (DEC-012).

---

## 5. Serving pipeline (online) — the 6-node LangGraph DAG

A single `FinSightState` TypedDict threads through six nodes (`src/retrieval/`):

| # | Node | Model | Responsibility |
|---|---|---|---|
| 1 | query_understanding | **Haiku** | Rewrite query self-contained; extract ticker + temporal reference |
| 2 | router | **Haiku** | Classify into 3 paths: earnings_analysis / financial_metrics / risk_and_events |
| 3 | retrieve | — | Hybrid BM25+dense, native Qdrant RRF fusion, ~20 candidates |
| 4 | rerank | Cohere | Cross-encoder rerank → top-k; + query-relative temporal boost + staleness flag |
| 5 | detect_conflicts | **Sonnet** | (intent-gated) extract numeric claims, flag cross-call contradictions |
| 6 | generate | **Sonnet** | Streamed answer, inline [N] citations, abstains if ungrounded; logs cost + failure mode |

**Cost-routing design:** cheap Haiku for classification/rewrite (nodes 1–2),
expensive Sonnet only for reasoning (nodes 5–6). Measured per-node latency makes
this concrete (Haiku ~700-900ms vs Sonnet generate ~5s).

**Served by FastAPI** (`api/main.py`): `/query` (full pipeline), `/query/stream`
(SSE token streaming; first token 4.3s end-to-end on the live deploy, DEC-018 —
DEC-011's ~1.3s was a Week-1 figure from before the pre-generation nodes existed),
`/recommend/{ticker}`, `/feedback`, `/health`. Lazy singletons + a `lifespan`
warmup avoid cold-start on the first real query.

**Clients:** the Streamlit demo (server-side) and the React frontend in
`frontend/` (browser, over CORS; `CORS_ALLOW_ORIGINS`, default `*`). The frontend
maps `[N]` to `chunks[N-1]` without re-sorting (DEC-020), falls back to a labeled
demo mode when `/health` fails (DEC-021), and runs a 9-case live behavioral eval
via `/query` (DEC-022).

---

## 6. Key design decisions & tradeoffs

Each is documented in full in [decisions.md](decisions.md); summarized here with
the tradeoff.

| Decision | Choice | Tradeoff / why |
|---|---|---|
| **Vector store** (DEC-002) | Qdrant | Native BM25+dense RRF in one query; free-tier cloud. Pinecone needs client-side fusion of two indexes. |
| **Embeddings** (DEC-003, 012) | voyage-finance-2 (API) + bge-m3 (local) | Domain-tuned + deploy-friendly (no model in the 512MB dyno). Fallback for offline/degraded. |
| **Retrieval** (DEC-013) | Hybrid BM25+dense, native RRF | +27.4% NDCG vs dense-only (measured). One server-side call, no client merge. |
| **Reranker** (DEC-006) | Cohere rerank-v3.5 + local ms-marco fallback | Managed quality, no GPU ops; graceful degradation on outage. |
| **Citations** (DEC-011) | Inline [N] parsed post-hoc, NOT forced tool-use | Forced tool-use buffers the whole JSON → kills streaming (first token 11s→1.3s, Week-1 generator path; live end-to-end TTFT is 4.3s, DEC-018). Production-idiomatic (Perplexity-style). |
| **Conflict detector** (DEC-007) | Intra-transcript, precision-gated | Cross-source needs SEC XBRL (not ingested). Precision gates (period/subject/date/chunk) kill false positives. |
| **Recency** (DEC-014) | Query-relative temporal boost | Historical corpus — "recent" = near the *queried* period, not wall-clock newest. Flags staleness → honest abstention. |
| **LLM provider** (DEC-010 → DEC-018) | Gateway switch: OpenRouter's Anthropic-compatible endpoint *or* Anthropic direct (`LLM_GATEWAY`) | DEC-010 rejected OpenRouter's OpenAI-compat layer (loses caching + tool use); DEC-018 uses its Anthropic-compatible Messages endpoint instead — same SDK, tool use and streaming. |
| **Self-contained serve** (DEC-012) | Full text in Qdrant payload; no DuckDB on deploy | Deploy needs no 664MB DuckDB, no local model → fits free tier. |

**Deliberately cut** (documented, not omitted): full-corpus chunking ablation,
Claude-vs-GPT bake-off (stale target), MLflow (one-shot ablations don't need it),
load-test run (cost). Cutting with a documented reason is itself the scope-discipline
signal.

---

## 7. Evaluation methodology

- **Golden set:** 50 queries — 40 corpus-grounded (generated *from* real chunks so
  a relevant chunk provably exists), 5 adversarial, 5 abstention.
- **Relevance labels:** LLM pooling (union top-k across configs, Claude judges each
  relevant/not) — standard IR pooling, honestly framed as LLM-labeled not human-gold.
- **Headline result:** hybrid+rerank beats dense-only by **+27.4% NDCG@10**
  (Recall@5 0.58→0.65, MRR 0.65→0.80). Nuance: hybrid captures most of the lift;
  rerank sharpens ordering (MRR/NDCG) more than coverage (Recall).
- **Faithfulness (anti-hallucination gate):** RAGAS **0.806** — passes the 0.80
  North-Star gate (Claude judge + Voyage embeddings).
- **CI:** lightweight per-push (ruff + serve-import guard + 29 unit tests, no API
  calls). The expensive RAGAS gate runs manually/pre-deploy by design. A separate
  `frontend-ci` workflow typechecks, runs 27 Vitest tests and builds `frontend/`.
- **Live behavioral suite** (DEC-022): 9 cases run from the frontend against the
  deployed API — expected behavior (ground / refuse / conflict node ran) + citation
  integrity. Complements RAGAS; doesn't replace it.

**Honesty layer** (DEC-015): every place a prettier number was possible (pad the
prompt for cache hits, drop low answer_relevancy, cherry-pick chunking labels), the
real number + reason was reported instead.

---

## 8. Deployment & operations

**Topology:** two Cloud Run services from one image (`finsight-api` + `finsight-ui`,
`min-instances=1`, DEC-019) → Qdrant Cloud (free 1GB, `finsight-prod`, ~158MB used)
→ external APIs (Claude via OpenRouter or Anthropic, Voyage, Cohere, LangSmith).
Secrets in Secret Manager under a dedicated service account (never committed). The
Render free-tier services remain as a backup. The React frontend (`frontend/`) is a
static build for any static host; it needs only its origin allowed by the API's
`CORS_ALLOW_ORIGINS` (default `*`).

**Self-contained serve:** `EMBEDDING_BACKEND=voyage` (no local model) +
`USE_DUCKDB_HYDRATION=false` (full text from Qdrant payload) → the app is a pure API
client that fits 512MB.

**Observability:** LangSmith per-node tracing; W&B Weave `@op` on all 6 nodes
(opt-in via `WEAVE_ENABLED`, DEC-017); per-query cost estimate
(`cost_tracker`) and 5-mode failure classification (`failure_tracker`) logged to
JSONL; `/feedback` captures thumbs up/down. Client-side, the frontend optionally
records per-query outcome / TTFT / latency / route / tokens / cost and uncaught
errors to insert-only Bolt Database (Supabase) tables — no question text (DEC-023).

**Resilience chain:** Voyage down → bge-m3 local; Cohere down → local cross-encoder
→ raw order; Claude down → pipeline nodes degrade to safe defaults; ungrounded →
abstain. No single dependency failure takes the system down silently.

**Known ops war stories** (in decisions.md): Qdrant `nofile` ulimit crash on bulk
ingest; corporate-proxy TLS bypass via certifi; the Cohere `rerank-english-v3.5`→
`rerank-v3.5` 404 (verify model IDs against the live API, don't guess); serve/local
requirements drift caught by a CI import-guard.

---

## 9. Scaling path & roadmap

**Scaling (interview answer, not built):**
- 100K q/day: Qdrant Cloud paid tier (horizontal); LLM cost bounded by cost-routing
  + prompt caching.
- 1M q/day: move rerank local to dodge the API ceiling; Anthropic Messages Batches
  for 50% cost on non-interactive load.
- Multi-tenant: Qdrant collection-per-tenant; OIDC SSO.

**Roadmap (next):**
1. Ingest SEC XBRL fundamentals → unlock the `financial_metrics` path and the
   **cross-source** conflict detector (transcript claim vs filed number) — the
   detector engine already supports it; it just needs Source B.
2. Conflict-aware retrieval mode (deliberately fetch a ticker's guidance + later
   actuals together) to raise live conflict recall.
3. Context Builder node (OHLCV event-window enrichment) + inline guardrails.

---

## 10. Tech stack summary

Python 3.11 · FastAPI · LangGraph · Qdrant (+ Qdrant Cloud) · DuckDB · Claude
(Sonnet 4.6 + Haiku 4.5, Anthropic SDK) · voyage-finance-2 / bge-m3 · Cohere
rerank-v3.5 / ms-marco-MiniLM · fastembed (BM25) · RAGAS · Streamlit · React 18 +
Vite + TypeScript + Tailwind + shadcn/ui + Recharts (frontend) · Vitest · Bolt
Database (telemetry only) · ruff + pytest + GitHub Actions CI · Cloud Run deploy
(Render backup).
