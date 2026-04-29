# FinSight — Multimodal Financial Evidence Engine

**Production RAG system for investor-grade financial research.** Answers questions across SEC filings, earnings call transcripts, OHLCV market data, and financial news — with cited sources, calibrated conflict detection across sources, guardrails, and P95 latency under 3 seconds at under $0.005/query.

**Live demo:** *(deploying Week 1 — URL here by end of Week 1)*
**Demo video:** *(Loom walkthrough in Week 5)*
**Status:** 🟦 Week 1 of 5 — scaffolding complete

---

## Why this project exists

Equity analysts spend 3–4 hours per research report cross-referencing three disconnected sources: what management said on the earnings call, what the filing actually disclosed, and how the market reacted. When those sources disagree — Q2 guidance vs Q3 guidance, transcript revenue vs 10-Q revenue — today's workflow has no systematic way to surface the conflict.

FinSight retrieves across all three modalities simultaneously, grounds every answer in cited sources, and flags when sources disagree. That last part — **evidence conflict detection** — turns this from a Q&A tool into a research product.

---

## Architecture

```
User query
   ↓
Input guardrails (PII + jailbreak)
   ↓
┌──────────────── LangGraph 6-node pipeline ────────────────┐
│ 1. Query Understanding  (Claude Sonnet, prompt-cached)    │
│ 2. Router              (Claude Haiku, 4-path classifier)  │
│ 3. Retriever           (Qdrant hybrid + Cohere Rerank)    │
│ 4. Context Builder     (DuckDB JOIN on ticker + period)   │
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
| Router LLM | Claude Haiku 4.5 | 10× cheaper for 4-class intent classification |
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

4 datasets across 4 modalities + 1 golden eval set:

| Modality | Dataset | Use |
|---|---|---|
| Earnings call transcripts | [Motley Fool scraped transcripts (Kaggle: tpotterer)](https://www.kaggle.com/datasets/tpotterer/motley-fool-scraped-earnings-call-transcripts) | Primary retrieval corpus. Conflict detector Source A |
| SEC structured filings | [SEC Financial Statement Data Sets (EDGAR XBRL)](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets) | DuckDB fundamentals. Conflict detector Source B |
| OHLCV prices | [Jackson Crow stock market dataset (Kaggle)](https://www.kaggle.com/datasets/jacksoncrow/stock-market-dataset) | `price_action` routing path. Event-window context |
| Market news | [Aaron7sun stock news (Kaggle)](https://www.kaggle.com/datasets/aaron7sun/stocknews) | `news_sentiment` routing path. Temporal context |
| Golden eval | Hand-curated | 50 queries + 20+20 conflict pairs + 5 adversarial + 5 abstention |

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

# Spin up Qdrant + MLflow
docker-compose up -d qdrant mlflow
```

### Ingest data (Week 1 Day 3+)
```bash
# Download Kaggle datasets to data/raw/
# (see docs/ingestion.md — Week 1 Day 3 artifact)

python -m src.ingestion.loader --source motley_fool
python -m src.indexing.ingest_vectors --corpus transcripts
```

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

### Run evals
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
│   ├── ingestion/           # Load raw → parquet/duckdb; temporal tagging
│   ├── indexing/            # Chunking; Qdrant upsert
│   ├── retrieval/           # Nodes 1-4: query understanding, router, retriever, context
│   ├── generation/          # Node 5: Sonnet streaming + structured citations
│   ├── insight/             # Evidence Conflict Detector — THE differentiator
│   ├── guardrails/          # Input + output safety
│   ├── recommendations/     # Shared-embedding related-tickers
│   ├── evaluation/          # RAGAS + ablations + LLM comparison
│   └── utils/               # Config, cost tracker, failure logger
├── api/                     # FastAPI async app
├── ui/                      # Streamlit 5-tab demo
├── evals/                   # Golden queries, conflict pairs, results
├── docs/
│   ├── PRD.md               # Problem, users, metrics, trade-offs
│   ├── architecture.md      # Diagrams, state schema, module boundaries
│   ├── decisions.md         # Engineering war stories — interview artifact
│   └── finsight_spec_v2.3.md  # Canonical spec
├── tests/
├── .github/workflows/       # eval.yml + lint.yml
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── requirements-serve.txt   # minimal runtime for Render
```

---

## Roadmap (5-week interview-scoped plan)

- **Week 1** — End-to-end skeleton + live Render URL *(in progress)*
- **Week 2** — Full retrieval pipeline (voyage, Cohere, LangGraph router, streaming, prompt caching)
- **Week 3** — Conflict detector + RAGAS evals + 3 ablations + CI gate
- **Week 4** — Production polish + related-tickers recs + load test + guardrails visible
- **Week 5** — Demo polish, Loom video, blog post, `decisions.md` finalized

Full plan: `docs/finsight_spec_v2.3.md`.

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
