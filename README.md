# FinSight — Multi-Source Financial Evidence Engine

**Production RAG system for investor-grade financial research.** Answers questions across three evidence sources — earnings call transcripts (text), SEC filings (structured fundamentals + 10-K risk factors), and OHLCV market data (time-series) — with cited sources, calibrated conflict detection across sources, guardrails, and P95 latency under 3 seconds at under $0.005/query.

**Built to know what it doesn't know:** it refuses when it can't ground an answer, flags stale evidence, and surfaces contradictions between sources instead of confidently averaging them.

**Live demo:** https://finsight-ui-z0mp.onrender.com — ask a question about 2019–2023 earnings calls and get a streamed, cited answer. *(Free-tier hosting: first request after ~15 min idle cold-starts in ~50s, then it's fast.)*
**API:** https://finsight-api-otsr.onrender.com/docs (FastAPI · `/query`, `/query/stream`, `/health`)
**Demo video:** *(Loom walkthrough in Week 5)*
**Status:** 🟩 Live — retrieval pipeline deployed (Week 1 gate cleared); LangGraph pipeline + conflict detector next (Week 2–3)

---

## Why this project exists

Equity analysts spend 3–4 hours per research report cross-referencing three disconnected sources: what management said on the earnings call, what the filing actually disclosed, and how the market reacted. When those sources disagree — Q2 guidance vs Q3 guidance, transcript revenue vs 10-Q revenue — today's workflow has no systematic way to surface the conflict.

FinSight retrieves across all three sources simultaneously, grounds every answer in cited sources, and flags when sources disagree. That last part — **evidence conflict detection** — turns this from a Q&A tool into a research product, and into a system that surfaces contradictions instead of confidently averaging them.

### Business value

In a regulated environment (SEC Rule 10b-5 liability on any numeric claim), a confident-but-wrong number is worse than a refusal — so the trust gates *are* the product:

- **Analyst value:** ~3 hrs/day saved × $200/hr × 20 days ≈ **$12K/month** of analyst time per seat.
- **Pricing:** $500/mo per seat (≈2.5% of a Bloomberg Terminal) → **~24× ROI** at the point of sale.
- **Unit economics:** ~$0.005/query × 50 queries/day × 20 days ≈ **$5/month cost** → **~99% gross margin**.

Full model and ICP in [docs/PRD.md](docs/PRD.md) §10.

---

## Architecture

```
User query
   ↓
Input guardrails (PII + jailbreak)
   ↓
┌──────────────── LangGraph 6-node pipeline ────────────────┐
│ 1. Query Understanding  (Claude Sonnet, prompt-cached)    │
│ 2. Router              (Claude Haiku, 3-path classifier)  │
│ 3. Retriever           (Qdrant hybrid + Cohere Rerank)    │
│ 4. Context Builder     (DuckDB JOIN + OHLCV event window) │
│ 5. Generator + Conflict Detector  (Sonnet streaming)      │
│ 6. Output Guardrails + Failure Mode Logger                │
└───────────────────────────────────────────────────────────┘
   ↓
Streaming cited answer + conflict report + metrics sidebar
```

Full architecture diagram in `docs/architecture.md`.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Vector store | Qdrant (Docker + Cloud) | Native hybrid BM25+dense in one index; free 1GB cloud tier; fastest metadata filtering |
| Primary embeddings | voyage-finance-2 | Domain-pretrained on SEC + earnings corpora. ~8–10% NDCG lift on financial retrieval |
| Fallback embeddings | BAAI/bge-m3 | MIT license; dense + sparse in one model; enables graceful degradation |
| Reranker | Cohere Rerank 3.5 | Managed cross-encoder quality; ~150ms; <$0.001/query |
| Fallback reranker | ms-marco-MiniLM-L-6-v2 | Local cross-encoder for Cohere-outage degradation |
| Orchestration | LangGraph | Stateful 6-node DAG with conditional branching; per-node LangSmith tracing |
| Primary LLM | Claude Sonnet 4.6 | Best citation-format enforcement; structured tool use |
| Router LLM | Claude Haiku 4.5 | 10× cheaper for 3-class intent classification (earnings / metrics / risk_and_events) |
| Prompt caching | Anthropic | ~60–80% cost reduction on static system prompt + tool defs |
| Structured outputs | Claude tool use + Pydantic | Citations and conflicts are schema-validated, not regex-parsed |
| Structured store | DuckDB | Columnar, 10–50× faster than Postgres/SQLite for OHLCV + fundamentals |
| Evals | RAGAS + 10 pytest assertions | Industry standard faithfulness + context precision; CI-gateable |
| Observability | LangSmith + MLflow | Per-node traces + experiment tracking |
| Serving | FastAPI (async) | Async handlers, Pydantic validation, connection pooling |
| Demo UI | Streamlit | Free public URL, 5-tab multi-scenario |
| Deployment | Render + Qdrant Cloud | Always-on live URL |
| CI/CD | GitHub Actions | RAGAS gate on every PR — fails if faithfulness < 0.75 |

---

## Data sources

3 evidence sources (text + structured + time-series) + 1 golden eval set:

| Source | Dataset | Use |
|---|---|---|
| Earnings call transcripts (text) | [Motley Fool scraped transcripts (Kaggle: tpotterer)](https://www.kaggle.com/datasets/tpotterer/motley-fool-scraped-earnings-call-transcripts) | `earnings_analysis` retrieval corpus. Conflict detector Source A |
| SEC filings (structured + risk text) | [SEC Financial Statement Data Sets (EDGAR XBRL)](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets) | `financial_metrics` (DuckDB fundamentals, conflict detector Source B) + `risk_and_events` (10-K Item 1A risk factors, 8-K events) |
| OHLCV prices (time-series) | [Jackson Crow stock market dataset (Kaggle)](https://www.kaggle.com/datasets/jacksoncrow/stock-market-dataset) | Node 4 universal context — event-window price moves for any path. Not its own router path (see decisions.md DEC-004) |
| Golden eval | Hand-curated | 50 queries + 20+20 conflict pairs + 5 adversarial + 5 abstention |

**Router paths:** `earnings_analysis` · `financial_metrics` · `risk_and_events`. The earlier `price_action` and `news_sentiment` paths were retired — OHLCV became universal Node-4 context and the Reddit-sourced news dataset was the wrong granularity (full rationale in [docs/decisions.md](docs/decisions.md) DEC-004).

**Data licensing note:** Motley Fool dataset is hosted on Kaggle under unclear commercial redistribution terms. For public demo deployment, we scope retrieval to SEC-only mode if licensing is ambiguous. See `docs/decisions.md`.

---

## Evaluation

| Metric | Target | Status |
|---|---|---|
| Faithfulness (RAGAS) | ≥ 0.80 | *measured end of Week 3* |
| Context precision | ≥ 0.75 | *Week 3* |
| Citation precision | ≥ 0.90 | *Week 3* |
| Hallucination rate | < 5% | *Week 3* |
| Abstention accuracy | ≥ 0.85 | *Week 3* |
| Conflict detection TPR | ≥ 0.80 | *Week 3* |
| Conflict detection FPR | ≤ 0.10 | *Week 3* |
| P95 latency | ≤ 3s | *measured Week 4 load test* |
| Cost per query | ≤ $0.005 | *measured Week 4* |

### Ablations (populated Week 3)

**Retrieval (target: hybrid+rerank beats dense-only by ≥ 10% NDCG)**

| Config | Recall@5 | MRR | NDCG@10 | Latency (ms) |
|---|---|---|---|---|
| BM25 only | — | — | — | — |
| Dense only (voyage-finance-2) | — | — | — | — |
| Hybrid (BM25 + Dense RRF) | — | — | — | — |
| Hybrid + Cohere Rerank | — | — | — | — |

**Chunking**

| Strategy | Recall@5 | NDCG@10 |
|---|---|---|
| Fixed 400-token | — | — |
| Sentence-aware | — | — |
| Paragraph | — | — |

**LLM comparison**

| Model | Faithfulness | Latency P95 | $/query |
|---|---|---|---|
| Claude Sonnet 4.6 | — | — | — |
| GPT-4o | — | — | — |

---

## Quickstart

### Prerequisites
- Python 3.11+
- Docker Desktop
- API keys: Anthropic, Voyage, Cohere, LangSmith (free tiers work for dev)
- Qdrant Cloud account (free 1GB tier) — only needed for public deploy

### Setup
```bash
# Clone
git clone https://github.com/aparmarthi/rag-hybrid-search-reranking-system.git finsight
cd finsight

# Environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Secrets
cp .env.example .env
# Edit .env with your API keys

# Spin up Qdrant (Docker Compose, or Colima, or the native `qdrant` binary)
docker-compose up -d qdrant mlflow
```

### Reproducing the data from a clean clone

Raw datasets (~8 GB) are gitignored — fetch them first, then run the pipeline.
`artifacts/ticker_universe.json` (the 76-ticker scope) **is** committed, so the
loaders filter correctly out of the box.

**1. Fetch raw sources → `data/raw/`:**
```bash
# Motley Fool earnings transcripts (manual Kaggle download):
#   kaggle.com/datasets/tpotterer/motley-fool-scraped-earnings-call-transcripts
#   → place motley-fool-data.pkl in data/raw/motley_fool/
# OHLCV prices (manual Kaggle download):
#   kaggle.com/datasets/jacksoncrow/stock-market-dataset
#   → place stock CSVs in data/raw/ohlcv/stocks/
# SEC EDGAR filings (automated):
python scripts/download_sec_edgar.py
```

**2. Load raw → DuckDB `documents` / `prices` tables:**
```bash
python -m src.ingestion.motley_fool_loader   # transcripts → documents
python -m src.ingestion.ohlcv_loader         # OHLCV → prices
python -m src.ingestion.sec_filing_parser    # 10-K/10-Q/8-K → documents
```

**3. Chunk + embed → DuckDB `chunks` + Qdrant dense vectors:**
```bash
# Embedding backend from EMBEDDING_BACKEND (.env): "voyage" (voyage-finance-2 API,
# primary — needs a Voyage key) or "bge-m3" (local, free, ~2 hrs on Apple MPS).
# Transcripts alone ≈ 15K chunks.
python -m src.indexing.ingest_vectors --doc-type earnings_transcript
# Smoke-test first with a subset:  --limit 10
# Wipe and start over:             python -m scripts.reset_chunks
# (If you switch backends after ingesting, re-embed in place: python -m scripts.reembed_chunks)
```

**4. Add BM25 sparse vectors → enables hybrid retrieval:**
```bash
python -m scripts.add_sparse_vectors          # local
```

**5. (For live deploy) push everything to Qdrant Cloud:**
```bash
# Copies dense+sparse vectors AND embeds full chunk text into the payload, so the
# deployed app is self-contained (no DuckDB, no local model). Needs QDRANT_CLOUD_*
# in .env. Then run: python -m scripts.add_sparse_vectors --cloud
python -m scripts.push_to_cloud
python -m scripts.add_sparse_vectors --cloud
```

After steps 1–4 the full pipeline runs locally (hybrid retrieve → rerank →
LangGraph → generate). Steps 5 is only needed to reproduce the live Render deploy.

### Run locally
```bash
# Terminal 1: API
uvicorn api.main:app --reload --port 8000

# Terminal 2: UI
streamlit run ui/streamlit_app.py
```

Or everything in Docker:
```bash
docker-compose up
```

Open http://localhost:8501 for Streamlit, http://localhost:8000/docs for API.

### Deploy (Render + Qdrant Cloud)
The live demo runs from `render.yaml` (two services: `finsight-api`, `finsight-ui`).
Secrets are set as Render dashboard env vars (never committed). Before deploying,
verify the trimmed runtime has every dependency the serve path imports:
```bash
python -m scripts.check_serve_imports   # guards against requirements-serve.txt drift
```

### Run evals *(Week 3 — not yet implemented)*
```bash
python -m src.evaluation.ragas_runner --golden evals/golden_queries.jsonl
python -m src.evaluation.ablation --config evals/ablation_configs/retrieval.yaml
```

---

## Repository layout

```
finsight/
├── data/                    # DVC tracked, gitignored if >50MB
├── notebooks/               # Exploration only (01_eda · 02_chunking_eval · 03_conflict_calibration)
├── src/
│   ├── ingestion/           # Load raw → DuckDB documents/prices (loaders + SEC parser)
│   ├── indexing/            # chunker, embedder (voyage/bge-m3), sparse BM25, Qdrant upsert
│   ├── retrieval/           # retriever (hybrid), reranker, LangGraph graph/nodes/state
│   ├── generation/          # Sonnet streaming + inline-citation parsing
│   ├── insight/             # Evidence Conflict Detector — THE differentiator (Week 3)
│   ├── guardrails/          # Input + output safety (Week 4)
│   ├── recommendations/     # Shared-embedding related-tickers (Week 4)
│   ├── evaluation/          # RAGAS + ablations + LLM comparison (Week 3)
│   └── utils/               # Config, logging
├── api/                     # FastAPI: /health, /query, /query/stream
├── ui/                      # Streamlit demo (single-query now; 5-tab in Week 4)
├── scripts/                 # data download, ingest iteration, sparse vectors, cloud push
├── docs/
│   ├── PRD.md               # Problem, users, metrics, trade-offs, ROI
│   ├── architecture.md      # Diagrams, state schema, module boundaries (✅/🔷 marked)
│   ├── decisions.md         # Engineering war stories — interview artifact (DEC-001…013)
│   ├── deployment-playbook.md   # How I'd deploy this at a regulated customer (FDE artifact)
│   ├── interview-positioning.md # Role → question → artifact map
│   └── finsight_spec_v2.3.md  # Canonical spec
├── artifacts/ticker_universe.json  # 76-ticker corpus scope (committed)
├── render.yaml              # Render blueprint (finsight-api + finsight-ui)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── requirements-serve.txt   # minimal runtime for Render deploy
```

---

## Roadmap (5-week interview-scoped plan)

- **Week 1** — ✅ End-to-end skeleton + live Render URL (voyage-finance-2 embeddings, streaming cited answers, abstention)
- **Week 2** — ✅ Full retrieval pipeline: hybrid BM25+dense (native RRF), Cohere Rerank 3.5 + local fallback, 5-node LangGraph pipeline (query-understanding → 3-path Haiku router → retrieve → rerank → generate), LangSmith tracing. 🔷 Remaining: temporal recency boost, SEC-corpus ingest for the metrics/risk paths.
- **Week 3** — Conflict detector + RAGAS evals + 3 ablations + CI gate
- **Week 4** — Production polish + related-tickers recs + load test + guardrails visible
- **Week 5** — Demo polish, Loom video, blog post, `decisions.md` finalized

Full plan: [docs/finsight_spec_v2.3.md](docs/finsight_spec_v2.3.md). How this project maps to specific roles — and how I'd deploy it at a real customer — is in [docs/interview-positioning.md](docs/interview-positioning.md) and [docs/deployment-playbook.md](docs/deployment-playbook.md).

---

## Future Work (scoped out of v2.3 for timeline; listed for awareness)

- Two-tower bi-encoder fine-tuning on Motley Fool analyst Q&A pairs — unified retrieval + recommendation backbone
- BEIR FiQA-2018 generalization benchmark
- 3-LLM consensus judge (Claude + GPT + Gemini) to reduce self-preference bias
- Arize Phoenix embedding cluster visualization
- DeepEval as second eval framework (pytest-native)
- Semantic chunking (SemanticChunker) as 4th chunking ablation row
- Int8 scalar quantization on Qdrant
- Related queries + personalized doc feed (v2.3 keeps only related tickers)
- 10-K Item 1 graph edges for competitor peer identification
- Llama 3.1 8B local/private deployment via Ollama
- Cohen's kappa human evaluation with inter-annotator agreement
- Adversarial test suite as separate module (v2.3 folds 5 adversarial queries into golden set)
- Multi-turn conversation memory compression for long sessions
- ahmedsta/data-retreiver chart-image modality

---

## About

Built by [Amey Parmarthi](https://www.linkedin.com/in/ameyparmarthi) — AI Deployment Strategist at Salesforce, leading Agentforce deployments at Fortune 500 scale in regulated industries.

Related portfolio project: [KKBox Customer Retention ROI Platform](https://amey-churn-predictor.streamlit.app/) — end-to-end production ML on 31GB subscription data, dual-policy decision engine netting $17,666 in simulated net ROI.

---

## License

MIT (code). Data sources retain their own licensing — see `docs/decisions.md` for data-licensing notes.
