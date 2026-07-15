> ⚠️ **ARCHIVED — superseded by `finsight_spec_v2.3.md`.** Kept for history only.
> Contains obsolete plans (4-path router, GPT-4o comparison, 12–16 week scope).
> The canonical current spec is v2.3.

# FinSight — Execution Spec v2.2 (Canonical)

**Multimodal Financial Evidence & Research Platform**
**Target roles:** FDE · AI Engineer · AI PM at Cohere, Glean, Harvey, Anthropic, Perplexity, Scale, Databricks, Writer, Palantir, W&B
**Comp target:** $350K–$500K+ TC
**Date:** 2026-04-26
**Supersedes:** v1 spec, stack audit, v2.1

This spec is the single source of truth. If v2.1 and this document disagree, this document wins.

---

## 0. What changed from v2.1

v2.1 was an 8.5/10 retrieval project. v2.2 closes the gaps that separate "impressive portfolio" from "production AI system engineer."

| Area | v2.1 | v2.2 |
|---|---|---|
| Eval depth | RAGAS + 2-LLM compare | RAGAS + DeepEval + 3-LLM consensus judge + adversarial + abstention + citation precision + BEIR generalization + Pareto cost/quality + Phoenix viz + small human eval |
| Prompt engineering | System prompt | Prompt caching + structured tool use + extended thinking on conflict detection |
| Chunking ablation | Fixed / sentence / paragraph | + semantic chunking (4-way) |
| Vector store config | HNSW default | + int8 quantization |
| Guardrails | Named only | Guardrails-AI + presidio + explicit adversarial test suite |
| Degradation story | None | Documented fallback chain: voyage→bge-m3→fail; Cohere→local MiniLM; Sonnet→Haiku |
| Business value | 1 UI tab | Full `docs/product_strategy.md`: TAM/SAM/SOM · competitive matrix · unit economics · WTP · moat · GTM · risk register |
| Recommendations | None | Shared-embedding recommendation layer: related queries + related tickers + doc feed. Two-tower Phase 6 unifies retrieval + recs. |
| Load test | 10 concurrent | 50–100 concurrent |
| Conflict threshold | Hand-tuned | Calibrated from labeled pairs |
| Data licensing | Not addressed | Documented + SEC-only fallback path |
| Golden set | 50 queries | 50 hand + 150 synthetic (RAGAS TestsetGenerator) = 200 total |

---

## 1. Project positioning

**One-line pitch:**
> "FinSight is a financial research platform with hybrid retrieval, domain-adapted embeddings, conflict-aware answers with structured citations, and a shared-embedding recommendation layer — evaluated with RAGAS + DeepEval + 3-LLM consensus judging, prompt-cached and cost-bounded, with graceful degradation and online feedback."

**Interview-ready framing:**
> "I built a system that reconciles what management said on the call, what the filing actually disclosed, and what the market did around that event — and flags when they disagree. And because the retrieval embeddings are shared with a recommendation layer, it doesn't just answer questions — it surfaces related tickers, related queries, and documents the analyst hasn't read yet. Same infrastructure, two ML products."

**Target user (primary):** Institutional equity analyst at a fund with <$1B AUM that can't afford Bloomberg ($24K/seat) or AlphaSense ($15K/seat).

**Secondary user:** Retail investor doing deep due diligence.

**Explicitly NOT building:** trading signals, portfolio management, general-purpose chatbot, real-time market data.

---

## 2. Product Requirements Document (PRD summary)

Full version lives at `docs/PRD.md`. Summary here for spec completeness.

| Field | Value |
|---|---|
| **Problem** | Equity analysts spend 3–4 hours/report cross-referencing transcripts, filings, and price data. Sources often conflict; no systematic surfacing. |
| **North Star metric** | Faithfulness ≥ 0.80 (RAGAS) at P95 ≤ 3s and cost ≤ $0.005/query |
| **Guardrail metrics** | Hallucination rate < 5% · Out-of-scope refusal rate > 90% · Context precision ≥ 0.75 · Temporal staleness < 10% · Citation precision ≥ 0.90 · Citation recall ≥ 0.85 · Abstention accuracy ≥ 0.85 |
| **Success criteria** | End-to-end cited answer in < 3s · Hybrid+rerank beats dense-only by ≥ 10% NDCG · Conflict detector catches ≥ 80% of known conflicts with < 10% false positive rate · Related-ticker recommendations achieve ≥ 0.60 precision@5 against analyst-labeled peer set |
| **Key trade-offs** | voyage-finance-2 (accuracy) > OpenAI (cost) · Cohere Rerank (managed) > self-hosted (free, ops) · LangGraph (observable, complex) > vanilla chain · Recency boost (freshness) > pure relevance · Structured tool-use citations (strict) > regex (brittle) · Prompt caching on (cost) > fresh every call (simplicity) |

---

## 3. Final tech stack (canonical)

Every row has a "why" — know it cold before interviews.

| Layer | Choice | Runner-up | Why |
|---|---|---|---|
| Vector store | **Qdrant (Docker + Cloud free tier)** | Pinecone | Native hybrid BM25+dense in one index; fastest metadata filtering; free cloud tier → live URL |
| Vector quantization | **int8 scalar quantization** | Full precision | ~4x memory savings, <1% recall loss — production cost awareness |
| Primary embeddings | **voyage-finance-2** | OpenAI text-embedding-3-large | Domain pretraining on SEC/earnings; 8–10% NDCG lift on financial retrieval |
| Local fallback embeddings | **BAAI/bge-m3** | all-MiniLM-L6-v2 | MIT license; strong open-source; dense+sparse in one model |
| Baseline embeddings (for ablation story) | **all-MiniLM-L6-v2** | — | Weak baseline; enables 3-tier progression story: MiniLM → Voyage → fine-tuned two-tower |
| Reranker (primary) | **Cohere Rerank 3.5** | ms-marco-MiniLM local | Managed quality; ~150ms; <$0.001/query; no GPU ops |
| Reranker (degraded mode) | **cross-encoder/ms-marco-MiniLM-L-6-v2** | — | Local fallback if Cohere is down |
| Orchestration | **LangGraph** | LangChain LCEL | Stateful DAG with conditional branching; per-node LangSmith tracing |
| Primary LLM | **Claude Sonnet 4.6** (`claude-sonnet-4-6`) | GPT-4o | Best instruction-following for citation enforcement; structured tool use |
| Router LLM | **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) | GPT-4.1-mini | 10x cheaper for 4-class intent classification |
| Conflict-detection LLM | **Claude Sonnet 4.6 with extended thinking** | Sonnet without thinking | Complex multi-hop numeric reasoning; precision > latency for this node |
| Prompt caching | **Anthropic prompt caching** | None | 60–80% cost reduction on repeated system prompt + tool defs; essential for interview credibility in 2026 |
| Structured outputs | **Claude tool use + Pydantic schemas** | Regex parsing | Citations and conflict reports are Pydantic-validated structured responses |
| LLM-as-judge (eval only) | **GPT-4o + Gemini 2.5 Pro** | Claude only | 3-model consensus reduces self-preference bias |
| Structured store | **DuckDB** | SQLite / Postgres | Columnar; 10–50x faster for OHLCV + fundamentals analytical queries; zero ops |
| Data versioning | **DVC** | LakeFS | Portfolio standard; git-native |
| Experiment tracking | **MLflow** | W&B | Ablation runs + parameter lineage |
| RAG evals | **RAGAS + DeepEval** | TruLens | RAGAS for exploration/batch; DeepEval for pytest CI gates |
| Eval viz | **Arize Phoenix** | TruLens dashboard | Free self-host; embedding cluster plots for README |
| Guardrails | **Guardrails-AI + presidio + LangSmith online evals** | NeMo Guardrails | Input PII/jailbreak + output faithfulness; no NVIDIA-stack lock-in |
| Observability | **LangSmith + MLflow** | Langfuse | LangSmith for traces; MLflow for experiments |
| Serving | **FastAPI (async) + Docker Compose** | LitServe | Async handlers + connection pooling; Pydantic validation |
| Demo UI | **Streamlit** | Gradio | Free public URL; clean multi-tab; streaming support |
| Deployment | **Render (always-on) + Qdrant Cloud free** | Railway | Live demo URL for recruiters |
| CI/CD | **GitHub Actions + DeepEval gates** | — | Fails PR if faithfulness < 0.75 or Recall@5 < 0.65 |
| Load testing | **locust** | k6 | Python-native; target 50–100 concurrent users |
| IDE | **Claude Code (Opus 4.7)** | Cursor | 200K context for full-codebase edits |

---

## 4. System architecture

### 4.1 Repo structure

```
finsight/
├── data/                        # Raw + processed (DVC tracked, gitignored if >50MB)
├── notebooks/                   # 01_eda · 02_chunking · 03_conflict_calibration · 04_embedding_viz
├── src/
│   ├── ingestion/
│   │   ├── loader.py
│   │   ├── schema.py            # DuckDB schema for fundamentals + prices
│   │   ├── temporal_tagger.py   # date · quarter · fiscal_year metadata
│   │   └── licensing_check.py   # verify dataset licensing before ingest
│   ├── indexing/
│   │   ├── qdrant_client.py     # int8 quantization config
│   │   ├── ingest_vectors.py
│   │   ├── chunker.py           # 4 strategies: fixed · sentence · paragraph · semantic
│   │   └── finetune/            # Phase 6 stretch
│   │       ├── extract_qa_pairs.py
│   │       └── train_biencoder.py
│   ├── retrieval/
│   │   ├── graph.py             # LangGraph StateGraph (6 nodes)
│   │   ├── query_understanding.py   # Node 1: rewriter + expander + decomposer
│   │   ├── router.py            # Node 2: 4-path Haiku classifier
│   │   ├── retriever.py         # Node 3: Qdrant hybrid + recency boost
│   │   ├── context_builder.py   # Node 4: DuckDB JOIN + staleness check
│   │   └── degradation.py       # fallback chain: voyage → bge-m3; Cohere → local MiniLM
│   ├── generation/
│   │   ├── generator.py         # Node 5: Sonnet streaming + prompt caching
│   │   ├── citation_parser.py   # structured tool-use → Pydantic CitationReport
│   │   └── tool_schemas.py      # Pydantic schemas for Claude tool use
│   ├── insight/
│   │   ├── conflict_detector.py # Sonnet with extended thinking
│   │   └── conflict_calibration.py  # threshold learning from labeled pairs
│   ├── guardrails/
│   │   ├── input_guard.py       # presidio PII + jailbreak + financial advice intent
│   │   ├── output_guard.py      # Guardrails-AI + hallucination filter
│   │   └── scope_checker.py
│   ├── recommendations/         # NEW in v2.2 — shared-embedding layer
│   │   ├── related_queries.py   # content-based: nearest queries in embedding space
│   │   ├── related_tickers.py   # content-based: nearest ticker centroids + graph edges
│   │   ├── doc_feed.py          # content-based personalized feed from query history
│   │   └── metrics.py           # precision@K, coverage, novelty, diversity
│   ├── evaluation/
│   │   ├── ragas_runner.py
│   │   ├── deepeval_pytest.py   # CI-gateable tests
│   │   ├── ablation.py
│   │   ├── consensus_judge.py   # 3-LLM consensus (Claude + GPT + Gemini)
│   │   ├── adversarial_suite.py # jailbreak · prompt injection · PII extraction
│   │   ├── abstention_eval.py   # 20 out-of-scope queries
│   │   ├── citation_eval.py     # precision + recall on numeric claims
│   │   ├── beir_check.py        # FiQA-2018 generalization check
│   │   ├── pareto_frontier.py   # cost × quality matrix
│   │   ├── phoenix_viz.py       # embedding cluster plots
│   │   ├── human_eval.py        # small labeled set for anchor
│   │   └── golden_set.py        # 50 hand + 150 synthetic = 200 queries
│   └── utils/
│       ├── logging.py
│       ├── config.py
│       ├── cost_tracker.py      # per-query token + API cost
│       ├── failure_tracker.py   # retrieval_miss / bad_ranking / hallucination / ambiguous_query / stale_data
│       └── cache.py             # prompt cache key management
├── api/
│   ├── main.py                  # FastAPI async
│   ├── routes.py                # /query · /health · /feedback · /recommend
│   └── middleware.py
├── ui/
│   └── streamlit_app.py         # 6 tabs (5 core + 1 recommendations)
├── evals/
│   ├── golden_queries.jsonl
│   ├── adversarial.jsonl
│   ├── abstention.jsonl
│   ├── conflict_pairs_labeled.jsonl
│   ├── human_labeled.jsonl
│   └── results/                 # timestamped runs
├── docs/
│   ├── PRD.md
│   ├── decisions.md             # 5+ engineering war stories
│   ├── architecture.md
│   ├── product_strategy.md      # TAM/SAM/SOM · competitive · unit econ · WTP · moat · GTM · risk
│   ├── eval_plan.md             # full eval taxonomy
│   └── finsight_spec_v2.2.md    # this file
├── tests/
│   ├── test_router.py
│   ├── test_citations.py
│   ├── test_conflict_detector.py
│   ├── test_query_understanding.py
│   ├── test_recommendations.py
│   ├── test_guardrails.py
│   ├── test_degradation.py      # simulate Voyage/Cohere outages
│   └── test_golden_regressions.py
├── .github/workflows/
│   ├── eval.yml                 # RAGAS + DeepEval gate
│   └── lint.yml
├── docker-compose.yml           # FastAPI + Qdrant + MLflow + Phoenix
├── requirements.txt
├── requirements-serve.txt       # minimal runtime
├── .env.example
└── README.md
```

### 4.2 Query flow — 6-node LangGraph pipeline

Every node independently observable in LangSmith with per-node latency and cost.

**Node 1 — Query Understanding**
Input: raw query.
- Rewriter: "AAPL Q3" → "Apple Q3 2024 earnings revenue guidance"
- Expander: synonyms for finance terms (EBITDA ↔ operating income, etc.)
- Multi-hop decomposer: compound queries → sub-queries (fan-out)
- Temporal reference detector: extracts absolute/relative dates
Output: rewritten query + sub-queries + time reference.

**Node 2 — Router**
Claude Haiku 4.5 classifies into one of: `earnings_analysis`, `financial_metrics`, `price_action`, `news_sentiment`. Sets `routing_path` state. Prompt cached.

**Node 3 — Retriever**
Qdrant hybrid BM25+dense with temporal metadata filter. Recency boost: last 2 quarters +0.15 on fused score. Cohere Rerank 3.5 on top-20 → top-5. Each chunk carries payload: `{source, ticker, date, doc_type, section}`. Degradation chain active: if Voyage API down → bge-m3; if Cohere down → local MiniLM reranker.

**Node 4 — Context Builder**
DuckDB JOIN on `ticker + period` appends fundamentals row (revenue, EPS, margins, guidance). Temporal staleness check: flags if best chunk > 2 quarters old.

**Node 5 — Generator + Conflict Detector**
- Claude Sonnet 4.6 streaming with prompt-cached system prompt + tool definitions
- Structured tool use: `emit_answer(answer, citations: list[Citation])` — Pydantic-validated
- Conflict detector runs in parallel: Sonnet with extended thinking scans chunks for contradictory KPIs
- If conflict found: UI surfaces "Sources disagree: [Transcript] $89.5B vs [SEC] $89.1B (delta $0.4B > $500M threshold)"

**Node 6 — Guardrails + Logging**
- Input guard (presidio PII + jailbreak): already ran pre-Node-1, results attached to state
- Output guard (Guardrails-AI): faithfulness score from RAGAS; flags if < 0.7
- Scope checker: flags out-of-domain
- Failure mode logger: classifies into 5 modes
- Thumbs up/down feedback → `feedback_log.jsonl`
- Full query log to LangSmith

---

## 5. The differentiators (what closes interviews)

### 5.1 Evidence Conflict Detector
Unchanged from v2.1 — still the #1 interview moment. v2.2 strengthens it with:
- **Extended thinking** on Sonnet for multi-hop numeric reasoning
- **Calibrated thresholds** learned from `evals/conflict_pairs_labeled.jsonl` (50 known-conflict + 50 known-clean pairs)
- **Source authority weighting**: SEC filing > earnings call > news > analyst note
- **Structured output**: `{metric, source_a, value_a, source_b, value_b, delta, authority_winner}`

### 5.2 Shared-embedding recommendation layer (NEW)
Reuses the same Qdrant index + Voyage embeddings. No new infra.

| Feature | Mechanism | Metric |
|---|---|---|
| **Related queries** | Log every query embedding → nearest-neighbor lookup in query-embedding index | Precision@5 on manually-labeled "semantically related" query pairs |
| **Related tickers** | Compute ticker centroid from all chunks for that ticker → nearest ticker centroids + graph edges (competitor/supplier from SEC 10-K Item 1) | Precision@5 vs analyst-labeled peer set (target ≥ 0.60) |
| **Doc feed** | User query history → aggregate embedding → nearest unread documents | Click-through rate on feedback loop |
| **Phase 6 stretch: two-tower model** | Fine-tune bi-encoder on Motley Fool Q&A — same model powers both retrieval (query-passage) AND recommendations (query-query, ticker-ticker) | Retrieval Recall@5 + rec Precision@5 both improve vs baseline |

**Interview framing:** "Retrieval and recommendations are the same problem — nearest neighbors in embedding space. I built both on shared infrastructure. Fine-tuning the two-tower model improves both systems at once."

### 5.3 Query Understanding node
Unchanged — still addresses #1 RAG failure mode.

### 5.4 Temporal awareness
Unchanged — recency boost + staleness check.

### 5.5 Failure mode logging + feedback loop
Unchanged — 5 failure categories + thumbs up/down → `feedback_log.jsonl`.

### 5.6 Graceful degradation (NEW)
Documented fallback chain in `src/retrieval/degradation.py` and `docs/decisions.md`:
- Voyage API down → bge-m3 local (warn in UI)
- Cohere down → local MiniLM reranker (warn in UI)
- Sonnet rate-limited → Haiku (warn in UI that quality is degraded)
- Qdrant Cloud down → local Qdrant via Docker
Interview answer: "A production AI system doesn't just work on the happy path."

---

## 6. Evaluation plan (expanded — the 10/10 eval story)

Full version in `docs/eval_plan.md`. Summary here.

### 6.1 Golden set construction
- 50 hand-curated queries (10 per routing path × 4 + 10 conflict detection)
- 150 synthetic queries generated via RAGAS `TestsetGenerator` from ingested corpus
- 20 abstention queries (out-of-scope: "What will AAPL close at tomorrow?", "Should I buy NVDA?")
- 50 known-conflict + 50 known-clean pairs for conflict calibration
- 20 adversarial (jailbreak + prompt injection + PII extraction)
- 20 human-labeled for anchor (inter-annotator agreement target ≥ 0.7 Cohen's kappa)

**Total:** 310 evaluation items across 6 test sets.

### 6.2 Metrics taxonomy

| Category | Metric | Target | Tool |
|---|---|---|---|
| Retrieval | Recall@5, Recall@10, MRR, NDCG@10 | Hybrid+rerank ≥ dense-only + 10% NDCG | Custom + RAGAS |
| Per-source retrieval | Recall@K broken down by doc_type | Document as finding | Custom |
| Generation | Faithfulness, answer relevancy, context precision, context recall | Faithfulness ≥ 0.80 | RAGAS |
| Citation | Precision, recall on numeric claims | Precision ≥ 0.90, recall ≥ 0.85 | Custom `citation_eval.py` |
| Abstention | Refusal accuracy on out-of-scope | ≥ 0.85 | Custom `abstention_eval.py` |
| Conflict detection | True positive rate on 50 known conflicts; false positive rate on 50 clean pairs | TPR ≥ 0.80, FPR ≤ 0.10 | Custom |
| Adversarial | Jailbreak resistance, PII leak rate | 0 leaks, ≥ 0.95 jailbreak resistance | Custom `adversarial_suite.py` |
| Generalization | NDCG on FiQA-2018 (public BEIR benchmark) | Sanity check — fine-tuned encoder should not catastrophically overfit | BEIR |
| Consensus judge | 3-LLM agreement (Claude + GPT + Gemini) on faithfulness | Agreement rate ≥ 0.75 | Custom |
| Human eval | Rubric score on 20 items | Correlation with RAGAS faithfulness ≥ 0.7 | Manual + agreement calc |
| Latency | P50, P95, P99 per node and end-to-end | P95 ≤ 3s | locust + LangSmith |
| Cost | $/query (embedding + rerank + LLM) | ≤ $0.005/query | Custom cost_tracker |
| Pareto | Cost × faithfulness matrix over {router-only, +rerank, +conflict, +extended-thinking} | Plot frontier | Custom `pareto_frontier.py` |
| Rec precision | Precision@5 on related-ticker vs analyst-labeled peers | ≥ 0.60 | Custom |
| Rec diversity | Intra-list diversity (1 - avg cosine similarity) | Report | Custom |
| Embedding quality | Arize Phoenix cluster viz colored by ticker + doc_type | Visual check for README | Phoenix |

### 6.3 Ablations (in `evals/results/` with MLflow tracking)

1. **Retrieval:** BM25-only vs dense-only vs hybrid vs hybrid+rerank (4 rows)
2. **Chunking:** fixed vs sentence vs paragraph vs semantic (4 rows)
3. **Embedding:** MiniLM vs Voyage vs fine-tuned two-tower (3 rows — Phase 6 completes this)
4. **Reranker:** no-rerank vs MiniLM-local vs Cohere (3 rows)
5. **Router vs no-router:** compare end-to-end quality + cost (2 rows)
6. **Prompt caching on/off:** cost comparison (2 rows)
7. **LLM comparison:** Sonnet vs GPT-4o vs Gemini 2.5 Pro on 50-query golden set (3 rows)
8. **Cost × quality Pareto:** {Haiku-only, Haiku+Sonnet, Sonnet-only} × {no-rerank, MiniLM, Cohere} (9 points)

Every ablation has: real numbers in `README.md`, MLflow run link, rationale in `decisions.md`.

### 6.4 CI gate (GitHub Actions)

On every PR:
- Run RAGAS on 20-query regression subset
- Run DeepEval pytest assertions
- Fail if: faithfulness < 0.75, citation precision < 0.85, Recall@5 < 0.65, any adversarial test fails

---

## 7. Business value & product strategy

Full version in `docs/product_strategy.md`. Summary:

### 7.1 Market sizing
- **TAM:** ~10K US equity analysts × $200K loaded cost × 3hr/day saved × 250 days = $1.5B/yr time savings
- **SAM:** Mid-market funds (<$1B AUM) + retail DD — ~50K seats × $500/mo = $300M/yr
- **SOM (3 yr):** 1% capture = $3M ARR

### 7.2 Competitive matrix

| Product | Price/seat | Hybrid retrieval | Conflict detection | Temporal awareness | Open eval harness |
|---|---|---|---|---|---|
| Bloomberg Terminal | $24K/yr | — | — | — | — |
| AlphaSense | $15K/yr | Yes (prop) | — | Partial | — |
| Hebbia | $$$ | Yes | — | — | — |
| BamSEC | $$ | Keyword | — | — | — |
| FactSet | $$$$ | — | — | — | — |
| **FinSight (this)** | $500/mo | Yes | **Yes** | **Yes** | **Yes** |

### 7.3 Unit economics (at 1K active users)
- Cost/query: $0.005
- Queries/analyst/day: 50
- Cost/analyst/month: ~$7.50
- Price/analyst/month: $500
- Gross margin: ~98%

### 7.4 Willingness-to-pay
3 hrs/day × $200/hr × 20 days = $12K/month time saved. Pricing at $500/mo = 24x ROI. Even at 10% of time actually recovered, $1,200/mo value vs $500 cost → 2.4x ROI.

### 7.5 Moat / defensibility
1. **Data flywheel:** query logs → feedback → better recs → retention
2. **Fine-tuned domain encoder:** two-tower trained on Motley Fool Q&A + feedback
3. **Eval harness as IP:** 200+ queries + conflict pairs is itself a data asset
4. **Integrations:** Slack bot, Notion export (v2 expansion)

### 7.6 Risk register
| Risk | Severity | Mitigation |
|---|---|---|
| Hallucination liability (Rule 10b-5) | High | Aggressive guardrails + faithfulness CI gate + explicit "not investment advice" disclaimer |
| Data licensing (Motley Fool on Kaggle) | Medium | Verify license; fallback to SEC-only mode if ambiguous |
| Model drift (embeddings stale) | Medium | Monthly regression suite + drift detection on new filings |
| API cost overruns | Medium | Cost tracker + per-user monthly budget + auto-degrade to cheaper tier |
| Regulation FD | Medium | Source cites only public filings + >30-day-old calls |
| Competitive moat erosion (Bloomberg copies) | Low | Small-fund ICP is underserved; Bloomberg unlikely to move down-market |

### 7.7 GTM
- **Beachhead ICP:** small L/S hedge funds ($100M–$1B AUM) priced out of Bloomberg
- **Acquisition:** content-led (write 10 FinSight-generated earnings deep-dives, link demo)
- **Pricing:** $500/mo flat + $0.01/query over 5K/mo
- **Expansion path:** portfolio alerts → team sharing → custom research agents → Slack bot

---

## 8. Build phases

### Phase 1 — End-to-end skeleton (Weeks 1–2)
- Repo structure · git init · DVC init · `.env.example` · `docs/PRD.md` + `docs/product_strategy.md` written BEFORE code
- Dataset licensing check (Motley Fool + yfinance); SEC-only fallback documented
- Docker Compose: FastAPI + Qdrant + MLflow + Phoenix
- Ingest earnings transcripts → fixed-size chunking → bge-m3 local embeddings → Qdrant upsert
- Single dense-only retrieval → Sonnet generation (no streaming yet, no caching) → structured citation tool
- FastAPI `/query` + `/health` + latency middleware
- Streamlit: single query box, cited answer visible

**Exit criteria:** end-to-end query returns cited answer in under 10s on localhost. PRD + product_strategy committed. Licensing verified.

### Phase 2 — Full retrieval pipeline (Weeks 2–3)
- Switch to voyage-finance-2 (keep bge-m3 in degradation path)
- Enable Qdrant hybrid BM25+dense with int8 quantization
- Add Cohere Rerank 3.5 (local MiniLM in degradation path)
- Ingest all 5 datasets; DuckDB schema with ticker JOIN
- LangGraph 4-path router (Haiku classifier + prompt caching)
- Query Understanding Node 1: rewriter + expander + decomposer
- Temporal metadata tagging + recency boost (+0.15 for last 2 quarters)
- LangSmith tracing wired on every node
- **Prompt caching** on Sonnet system prompt + tool defs
- **Streaming** responses via FastAPI `StreamingResponse` + Streamlit `st.write_stream`

**Exit criteria:** all 4 routing paths work. Streaming visible. LangSmith full trace visible. Prompt cache hit rate > 80%. Degradation paths tested via simulated API outages.

### Phase 3 — Insight layer + eval foundation (Weeks 3–4)
- Evidence Conflict Detector with extended thinking + calibrated thresholds from labeled pairs
- Conflict UI in Streamlit (inline in answer)
- **Golden eval set construction:** 50 hand + 150 synthetic (RAGAS TestsetGenerator) + 20 abstention + 20 adversarial + 50+50 conflict pairs + 20 human-labeled
- RAGAS runner: faithfulness, context precision, answer relevancy
- DeepEval pytest gates
- Ablations 1–4: retrieval · chunking (incl. semantic) · embedding baseline · reranker
- MLflow logging every run
- GitHub Actions RAGAS + DeepEval gate

**Exit criteria:** 4 ablation tables with real numbers. Conflict detector calibrated (TPR ≥ 0.80, FPR ≤ 0.10). CI gate green on main.

### Phase 3.5 — Recommendation layer (Week 4.5) — NEW
- `src/recommendations/related_queries.py` — log query embeddings to Qdrant, nearest-neighbor API
- `src/recommendations/related_tickers.py` — ticker centroids + graph edges from 10-K Item 1 competitor mentions
- `src/recommendations/doc_feed.py` — personalized feed from query history
- Streamlit Tab 6: "Related" — related queries sidebar + related tickers panel + doc feed
- Metrics: precision@5 on manually-labeled related-ticker pairs (target ≥ 0.60)

**Exit criteria:** related-ticker panel returns sensible peers for top 20 tickers. Metric ≥ 0.60 documented in README.

### Phase 4 — Production hardening (Weeks 5–6)
- Failure mode logger (5 categories)
- Thumbs up/down feedback → `feedback_log.jsonl`
- Cost tracker in `src/utils/cost_tracker.py` (embedding + rerank + LLM tokens)
- Guardrails visible in UI: grounded / flagged / refused / stale / degraded-mode warning
- Multi-turn: last 3 turns with compression strategy for long conversations
- Pytest suite: all modules + golden regressions
- Adversarial eval suite
- Abstention eval
- Citation precision/recall eval
- **3-LLM consensus judge** (Claude + GPT + Gemini) on faithfulness
- **BEIR FiQA-2018 generalization check**
- **Pareto cost×quality frontier** plot
- **Phoenix embedding cluster viz** screenshot for README
- **Human eval** on 20 items
- Load test with locust: **50–100 concurrent users** (not 10); document P50/P95/P99 and bottleneck

**Exit criteria:** load test at 50 concurrent documented. All 6 evaluation test sets run. Pareto frontier plotted. Phoenix screenshot in README.

### Phase 5 — Demo polish + deployment (Weeks 6–7)
- Streamlit 6-tab demo:
  - Tab 1: Earnings Analysis ("What did Apple say about iPhone margins in Q3 2024?")
  - Tab 2: Financial Metrics ("Microsoft revenue and EPS trend last 4 quarters")
  - Tab 3: Evidence Conflict ("Did Nvidia Q3 guidance match Q2 guidance?") ← differentiator
  - Tab 4: Price + News ("What drove Tesla stock movement in October 2024?")
  - Tab 5: Recommendations ("Analyze NVDA" → related tickers, related queries, unread docs)
  - Tab 6: Business Value (analyst time savings, cost/query, ROI calculator)
- Metrics sidebar: routing path · latency per node · cost · retrieval count · failure mode · conflict Y/N · degraded-mode flag
- Deploy: Render always-on + Qdrant Cloud free tier
- `docs/decisions.md` with 5+ war stories (licensing pivot, Voyage outage simulation, conflict calibration, Pareto frontier finding, rec precision tuning)
- README: architecture diagram + ablation tables + Phoenix screenshot + live demo link + quick start
- Multi-LLM eval table in README

**Exit criteria:** live URL works without setup. README passes 30-second scan. decisions.md tells the engineering story.

### Phase 6 — Stretch (post-launch)
- Two-tower fine-tuning on Motley Fool Q&A pairs → unified retrieval + recommendation backbone
- Analyst Summary Generator: bull case / bear case / key risks
- Daily ingestion pipeline with scheduler
- Llama 3.1 8B via Ollama as local/private deployment (NOT Llama 4 Scout — won't fit on RTX 4060)
- Slack bot
- Portfolio monitoring / alerting

---

## 9. Interview decision questions (memorize cold)

v2.1's 10 questions stand. v2.2 adds these:

11. **Why prompt caching, and what's your cache hit rate?** "System prompt + tool definitions are static across queries. Caching them reduces cost ~60–80%. We measure hit rate in cost_tracker — currently [X]%. Without caching this project wouldn't meet the $0.005/query target."

12. **How do you prevent self-preference bias when using Claude to judge Claude?** "3-LLM consensus: Claude + GPT-4o + Gemini 2.5 Pro score the same responses. Agreement rate is the truth signal. I also have 20 human-labeled items as an absolute anchor — RAGAS faithfulness correlates with human ratings at [X]."

13. **How do you handle production outages of Voyage or Cohere?** "Graceful degradation. Voyage down → bge-m3 local embeddings with a banner warning the user quality is degraded. Cohere down → local ms-marco-MiniLM reranker. Sonnet rate-limited → Haiku with a warning. Documented in docs/decisions.md and tested in tests/test_degradation.py."

14. **How does your recommendation layer relate to retrieval?** "Retrieval and recommendation are the same problem — nearest neighbors in embedding space. I reuse the Qdrant index. Query → related queries is nearest-neighbor in query embedding space. Ticker → related tickers is nearest-neighbor in ticker centroid space plus graph edges from 10-K competitor mentions. Phase 6 fine-tunes a two-tower model that improves both simultaneously."

15. **Why did you skip Llama 4 Scout as the local LLM?** "Scout is 109B total / 17B active MoE. Doesn't fit in 8GB VRAM on RTX 4060 — the audit got this wrong. I'd use Llama 3.1 8B or Gemma 2 9B for local. For the portfolio demo, local LLM adds no interview signal over Claude API. Listed as Phase 6 stretch with the right model, not a core requirement."

16. **What's your biggest technical risk and what's the mitigation?** (Unchanged but expanded) "Two: conflict detection false positives from rounding — mitigated via calibrated per-metric thresholds from 50+50 labeled pairs. And data licensing ambiguity on Motley Fool Kaggle — mitigated via SEC-only fallback mode documented in decisions.md."

17. **How would you scale this to 100K users?** "Qdrant Cloud horizontal scaling. Prompt caching already at 80%+ hit rate → LLM cost per query stays bounded. Rerank is the bottleneck — would move to local cross-encoder on GPU at scale. DuckDB replaced by read-replicated Postgres for metadata. Streaming stays. CDN for static UI. This is a cost story, not an architecture story — FinSight's architecture already works at 100K."

---

## 10. Definition of Done (v2.2)

All v2.1 boxes plus:

- [ ] `docs/PRD.md`, `docs/product_strategy.md`, `docs/decisions.md`, `docs/eval_plan.md` all written
- [ ] Dataset licensing verified and documented
- [ ] Prompt caching active with hit rate > 80% documented
- [ ] Structured tool use for citations (Pydantic-validated)
- [ ] Extended thinking on conflict detector
- [ ] int8 quantization on Qdrant
- [ ] Graceful degradation tested for Voyage, Cohere, Sonnet (3 outage scenarios)
- [ ] 200+ golden queries + 20 adversarial + 20 abstention + 50+50 conflict pairs + 20 human-labeled
- [ ] 3-LLM consensus judge run on golden set
- [ ] Adversarial eval suite passes (0 PII leaks, jailbreak resistance ≥ 0.95)
- [ ] Abstention accuracy ≥ 0.85 on 20 out-of-scope queries
- [ ] Citation precision ≥ 0.90, recall ≥ 0.85
- [ ] BEIR FiQA-2018 sanity check run
- [ ] Pareto cost×quality frontier plotted in README
- [ ] Phoenix embedding cluster screenshot in README
- [ ] Human eval on 20 items with inter-annotator agreement ≥ 0.7
- [ ] Load test at **50+** concurrent users documented (not 10)
- [ ] Related-ticker recommendations at precision@5 ≥ 0.60
- [ ] Recommendation tab live in Streamlit
- [ ] Semantic chunking included in chunking ablation (4-way not 3-way)
- [ ] Conflict detector calibrated from labeled pairs (TPR ≥ 0.80, FPR ≤ 0.10)
- [ ] All v2.1 definition-of-done items

Total: 23 v2.1 items + 22 v2.2 additions = **45 items**.

---

## 11. Known open questions (resolve before Phase 1)

1. **Motley Fool Kaggle license** — commercial redistribution unclear. Verify before ingest; fall back to SEC-only if ambiguous.
2. **yfinance TOS** — Yahoo prohibits redistribution of OHLCV in commercial products. For demo = fine. For live public URL = borderline. Alternative: Stooq.com free bulk download.
3. **Qdrant Cloud free tier sizing** — 1GB limit. Full corpus may exceed. May need to (a) subset to top 500 tickers or (b) pay $25/mo.
4. **Claude prompt caching latency** — typically saves cost not latency. Verify first-token latency doesn't degrade.
5. **3-LLM judge cost** — running Gemini + GPT-4o + Claude on 200-query eval = non-trivial API spend. Budget ~$50 per full eval run; run nightly max.

---

**End of v2.2 spec.** This is canonical. Any conflict with v1, v2.1, or the stack audit: this document wins.
