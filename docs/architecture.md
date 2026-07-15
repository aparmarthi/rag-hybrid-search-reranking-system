# FinSight — Architecture

**Canonical spec:** `docs/finsight_spec_v2.3.md`
**Last updated:** 2026-07-14 (Weeks 1–4 complete — full pipeline + conflict detector + evals live)

**Legend:** ✅ implemented & live · 🔶 partial · 🔷 planned. This doc describes
what's actually built; planned nodes are marked so it stays honest to a reviewer.

---

## High-level diagram

```mermaid
flowchart TB
    U[User Query] --> N1[Node 1 ✅<br/>Query Understanding — Haiku<br/>rewrite + ticker + temporal ref]
    N1 --> N2[Node 2 ✅<br/>Router — Haiku, 3-path]
    N2 --> N3[Node 3 ✅<br/>Retrieve<br/>Qdrant hybrid BM25+dense RRF]
    N3 --> N4[Node 4 ✅<br/>Rerank + temporal boost<br/>Cohere 3.5 + local fallback]
    N4 --> N5[Node 5 ✅<br/>Detect Conflicts<br/>the differentiator]
    N5 --> N6[Node 6 ✅<br/>Generate — Sonnet 4.6<br/>inline citations, streaming]
    N6 --> R[Response<br/>Streaming + Citations + Conflicts]

    IG[Input Guardrails 🔷<br/>PII + jailbreak] -.planned.-> N1
    CB[Context Builder 🔷<br/>DuckDB fundamentals + OHLCV] -.planned.-> N4
    OG[Output Guardrails 🔷<br/>faithfulness + failure log] -.planned.-> R

    QD[(Qdrant Cloud ✅<br/>15,023 pts · dense + BM25 sparse<br/>+ full text in payload)] --- N3
    LS[LangSmith ✅<br/>per-node tracing] -.->  N1
    LS -.-> N6

    style N5 fill:#ffe4b5
    style N3 fill:#e0f2fe
```

The current live pipeline is the 6-node chain N1→N6 (conflict detection is gated
on comparison/guidance-intent queries — DEC-007). The Context Builder and
guardrail nodes remain planned (Week 4+) and slot into the same `StateGraph`.

---

## Data flow

### Ingestion pipeline (offline, run once per data refresh)

```
Raw sources                Processed                 Indexed
-----------                ---------                 -------
Motley Fool .pkl    -->    documents (DuckDB)  -->   chunks (DuckDB)  -->  Qdrant
                                                     + voyage-finance-2 dense vec
                                                     + BM25 sparse vec
                                                     + full text in payload
OHLCV .csv          -->    prices (DuckDB)     -->   (Node-4 context, planned)
SEC EDGAR .htm      -->    documents (DuckDB)  -->   (financial_metrics /
                                                      risk_and_events, planned)
```

Loaders (`src/ingestion/`) populate DuckDB `documents`/`prices`. The indexing
pipeline (`src/indexing/`) chunks + embeds → DuckDB `chunks` + Qdrant. Utility
and deployment scripts live in `scripts/` (see README "Reproducing the data").

**Current corpus:** earnings-call transcripts only — 15,023 chunks across 76
tickers (2019–2023). SEC fundamentals + 10-K risk factors are fetched but not
yet chunked/indexed, so the `financial_metrics` / `risk_and_events` paths route
correctly but abstain until that corpus lands.

### Query pipeline (online, per user request) — CURRENT

```
raw query
  └─> LangGraph StateGraph.invoke()   (src/retrieval/graph.py)
       │
       ▸ Node 1 ✅ Query Understanding (Haiku)
       │   - Rewrite to a self-contained, retrieval-friendly query
       │   - Extract ticker hint + temporal reference (drives query-relative recency)
       │
       ▸ Node 2 ✅ Router (Haiku, 3-path)
       │   - Classify into {earnings_analysis, financial_metrics, risk_and_events}
       │   - Cheap Haiku classification (the cost-routing story)
       │
       ▸ Node 3 ✅ Retrieve (hybrid)
       │   - Qdrant native RRF fusion: dense (voyage-finance-2) + BM25 sparse
       │   - One server-side query; prefetch ~20 candidates
       │
       ▸ Node 4 ✅ Rerank (+ temporal boost + staleness)
       │   - Cohere rerank-v3.5 (primary) → top-k; local ms-marco fallback on error
       │   - Query-relative recency boost; staleness flag if evidence off-period
       │
       ▸ Node 5 ✅ Detect Conflicts (the differentiator)
       │   - Gated on comparison/guidance intent (extraction is ~14s — skip otherwise)
       │   - Extract numeric claims → flag cross-call contradictions (precision-gated)
       │
       ▸ Node 6 ✅ Generate (Sonnet 4.6)
       │   - Streaming; inline [N] citations parsed to structured Citations
       │   - Abstains ("INSUFFICIENT EVIDENCE") when chunks don't support an answer
       │   - Computes per-query cost + logs failure-mode classification

streaming response to client (FastAPI /query, /query/stream → Streamlit)
```

### Planned nodes (Week 4+) — slot into the same graph

- 🔷 **Input guardrails** (before Node 1): Presidio PII scan + jailbreak check
- 🔷 **Context Builder** (after Node 4): DuckDB JOIN for fundamentals; OHLCV
  event-window enrichment (universal context, per DEC-004 — not a router path)
- 🔷 **Output guardrails** (after Node 6): RAGAS faithfulness gate in the request
  path (currently a manual/offline eval, not an inline node)

---

## State schema (LangGraph) — CURRENT

Actual schema in `src/retrieval/graph_state.py`:

```python
RoutingPath = Literal["earnings_analysis", "financial_metrics", "risk_and_events"]

class FinSightState(TypedDict, total=False):
    # Input
    raw_query: str
    top_k: int
    # Node 1 — Query Understanding
    rewritten_query: str
    ticker_hint: Optional[str]
    temporal_reference: Optional[dict]   # {year, quarter} — query-relative recency
    # Node 2 — Router
    routing_path: RoutingPath
    # Node 3 — Retrieve (hybrid)
    candidates: list[RetrievedChunk]
    # Node 4 — Rerank (+ temporal boost + staleness)
    reranked: list[RetrievedChunk]
    staleness_flag: bool
    # Node 5 — Detect Conflicts
    conflicts: list[dict]
    # Node 6 — Generate
    answer: str
    citations: list[Citation]
    grounded: bool
    # Observability
    latency_ms: dict[str, int]     # per-node
    tokens: dict[str, int]
    cost_usd: float
    failure_mode: str
```

**Planned additions (Week 4+):** `fundamentals_row`, `price_window` (Context
Builder), `faithfulness_score`, `guardrail_flags` (inline guardrails).

---

## Module boundaries

| Module | Responsibility | Key files | Status |
|---|---|---|---|
| `src/ingestion/` | Load raw → DuckDB `documents`/`prices` | `motley_fool_loader.py`, `ohlcv_loader.py`, `sec_filing_parser.py`, `schema.py` | ✅ |
| `src/indexing/` | Chunk, embed (voyage/bge-m3), sparse BM25, Qdrant upsert | `chunker.py`, `embedder.py`, `ingest_vectors.py`, `qdrant_client.py` | ✅ |
| `src/retrieval/` | Hybrid retrieval, rerank, LangGraph pipeline | `retriever.py`, `reranker.py`, `graph.py`, `graph_state.py`, `nodes.py` | ✅ |
| `src/generation/` | Sonnet generation + inline citation parsing | `generator.py` | ✅ |
| `src/insight/` | Evidence Conflict Detector (differentiator) | `conflict_detector.py` | ✅ |
| `src/guardrails/` | Input + output safety | `input_guard.py`, `output_guard.py` | 🔷 Week 4+ |
| `src/recommendations/` | Shared-embedding related tickers | `related_tickers.py` | ✅ |
| `src/evaluation/` | Golden set + ablations + RAGAS + faithfulness judge | `golden_set.py`, `ablation.py`, `ragas_runner.py`, `chunking_ablation.py`, `faithfulness.py`, `llm_compare.py` | ✅ |
| `src/utils/` | Config, logging, cost + failure trackers | `config.py`, `logging.py`, `cost_tracker.py`, `failure_tracker.py` | ✅ |
| `api/` | FastAPI async serving | `main.py` (`/health`, `/query`, `/query/stream`, `/recommend`, `/feedback`) | ✅ |
| `ui/` | Streamlit 5-tab demo | `streamlit_app.py` | ✅ |

Node functions (`query_understanding`, `router`, `retrieve`, `rerank`,
`generate`) all live in `src/retrieval/nodes.py` — not separate files.

---

## Observability

- **LangSmith** ✅ traces every node when `LANGSMITH_TRACING=true` +
  `LANGSMITH_API_KEY` set. Project: `finsight-dev`.
- **Per-node latency** ✅ captured in `FinSightState.latency_ms` and returned in
  the `/query` response (`latency_per_node_ms`).
- **MLflow** 🔷 ablation-run tracking — Week 3.
- **Cost / failure trackers** 🔷 `src/utils/` — Week 4.

---

## Deployment topology

### Dev (local)

```
localhost
  finsight-ui (Streamlit) :8501  ──>  finsight-api (FastAPI) :8000
                                          ├──> Qdrant (Colima/Docker :6333, or Cloud)
                                          └──> External APIs: Anthropic / Voyage / Cohere / LangSmith
```

Qdrant runs via Colima or Docker Compose locally (DEC: Colima chosen — no Docker
Desktop account needed). bge-m3 embeddings available locally as the Voyage fallback.

### Prod (Render + Qdrant Cloud) — LIVE

```
Render (free tier)                         Qdrant Cloud (free 1GB, finsight-prod)
  finsight-api  (FastAPI)  ──────────────>  15,023 pts · dense + BM25 sparse
  finsight-ui   (Streamlit) ──> API              + full chunk text in payload
        │
        └──> External APIs: Anthropic (Sonnet+Haiku) / Voyage / Cohere / LangSmith
```

**Self-contained serve (no local model, no DuckDB):** deploy uses the Voyage API
for embeddings (no bge-m3 model in the 512MB dyno) and reads full chunk text from
the Qdrant payload (no 664MB DuckDB shipped). `USE_DUCKDB_HYDRATION=false`,
`EMBEDDING_BACKEND=voyage`. Cold-start (~50s after 15-min idle) mitigated by an
external cron pinging `/health`.

---

## Scaling path (interview answer, not v2.3 work)

- **100K queries/day:** Qdrant Cloud paid tier (horizontal); LLM cost bounded by
  prompt caching once the pipeline prompt clears the cache-min threshold.
- **1M queries/day:** move Cohere Rerank local to avoid API ceiling; batch to
  Anthropic Messages Batches API for 50% cost reduction.
- **Multi-tenant:** Qdrant collection-per-tenant; SSO via OIDC.
- **Real-time ingestion:** EDGAR RSS + incremental Qdrant upsert.

---

## Versioning

- Code: git tags (semver)
- Models: pinned in `.env` (`ANTHROPIC_PRIMARY_MODEL`, `ANTHROPIC_ROUTER_MODEL`,
  `VOYAGE_MODEL`, `COHERE_RERANK_MODEL`)
- Data: gitignored; regenerable via the README reproduction runbook
