# FinSight — Execution Spec v2.3 (Interview-Scoped)

**Multimodal Financial Evidence Engine**
**Timeline:** 5 weeks at 15-20 hrs/week = 75-100 hours total
**North star:** interview-credibility, not spec completeness
**Target outcome:** shippable live demo + 3 ablation tables + conflict detector + 1 blog post + 90-sec demo video, ready to defend in Principal SA / FDE interviews
**Date:** 2026-04-26
**Supersedes:** v2.2 (which was over-scoped at 12-16 weeks / 45 DoD items)

---

## 0. Why v2.3 exists

v2.2 was a 10/10 RAG spec. It was also a 12-16 week commitment when the user needs to be interviewing in 3-4 weeks. A half-built 10/10 is worse than a complete 8/10. Interviewers see what ships, not what's in the spec.

v2.3 cuts ~55% of v2.2's scope, keeping only what drives interview moments. Anything that doesn't materially affect the 30-second demo impression or the 45-min architecture whiteboard is deferred to "future work" in README.

---

## 1. What survives from v2.2 (the interview-driving core)

| Kept | Why it stays |
|---|---|
| 6-node LangGraph pipeline | The architecture story |
| Qdrant hybrid BM25+dense | The "why Qdrant" question |
| voyage-finance-2 + bge-m3 fallback | The "why domain embeddings" question |
| Cohere Rerank 3.5 | Two-stage retrieval signal |
| Claude Sonnet 4.6 primary + Haiku 4.5 router | Cost-routing story (~55% reduction) |
| Prompt caching | Production-thinking signal, essential in 2026 |
| Structured tool use for citations (Pydantic) | Beats regex; defensible |
| Evidence Conflict Detector | THE differentiator — #1 interview moment |
| Query Understanding Node 1 | Addresses #1 RAG failure mode |
| Temporal recency boost + staleness check | Domain awareness signal |
| RAGAS eval harness | MLOps signal |
| LangSmith tracing | Observability signal |
| Failure mode logger | Production-thinking signal |
| Streaming responses | First-token latency < 500ms feels fast |
| Thumbs up/down feedback | Product-thinking signal |
| Live Render deploy + public URL | Single highest-leverage artifact |
| 3 ablation tables (retrieval, chunking, reranker) | The rigor story |
| Multi-LLM eval: Claude vs GPT-4o | Evaluation discipline |
| PRD + decisions.md | AI PM signal |
| Minimal recommendation layer (related tickers only) | "Two ML products on shared infra" story |
| Graceful degradation (documented, not fully tested) | FDE signal |

## 2. What's cut from v2.2 (and why)

| Cut | Replacement / Rationale |
|---|---|
| DeepEval as second eval framework | RAGAS alone + 10 pytest assertions suffice for interview credibility |
| 3-LLM consensus judge (Claude+GPT+Gemini) | Claude vs GPT-4o 2-way compare is sufficient; cuts ~2 days + API cost |
| BEIR FiQA-2018 generalization check | Defer to "future work" in README |
| Arize Phoenix embedding viz | One t-SNE plot using matplotlib is enough |
| Human eval with Cohen's kappa on 20 items | Spot-check 5 responses manually; skip formal agreement calc |
| Adversarial suite as separate module | 5 adversarial queries inline in golden set |
| Abstention eval as separate 20-query set | 5 out-of-scope queries in golden set |
| Citation precision/recall as separate metric | RAGAS faithfulness covers ~80% of the story |
| Full Pareto cost×quality frontier | One ablation table row comparing {Haiku-only, Haiku+Sonnet, Sonnet-only} |
| Extended thinking on conflict detector | Standard Sonnet is enough; thinking adds latency + complexity |
| Int8 quantization on Qdrant | Defer to stretch; no interview leverage |
| Semantic chunking as 4th ablation row | 3-way ablation (fixed/sentence/paragraph) is enough |
| 200+ golden queries | 50 hand-curated is enough — every interview ablation table shows 50-query eval |
| 50+50 conflict pair calibration | 20 known-conflict + 20 clean pairs; simpler threshold calibration |
| Load test at 50-100 concurrent | 30 concurrent is credible; same locust setup effort |
| Multi-turn with compression strategy | Last-3-turn simple version |
| Fully-tested degradation scenarios | Document fallback chain in decisions.md; build it but skip outage simulation tests |
| Related queries + doc feed recommendations | Keep only related tickers (ticker centroids + nearest-neighbor); 2 days not 5 |
| 10-K graph edges for competitor mentions | Use voyage embeddings only for related tickers; skip graph work |
| Two-tower Phase 6 | Drop entirely from spec; mention verbally in interviews as "next direction" |
| Llama 4 Scout local LLM | Drop entirely; no interview leverage and hardware-incompatible anyway |
| Full adversarial test suite | 5 hand-crafted adversarial queries suffice |
| Conflict detector source-authority weighting | Flat detection; discuss weighting verbally in interviews |

**Net effect:** v2.3 is ~45% of v2.2's scope, all the interview moments intact.

---

## 3. Final tech stack (locked, no more revisions)

| Layer | Choice | Why (know cold) |
|---|---|---|
| Vector store | Qdrant (Docker local + Cloud free tier for public demo) | Native hybrid BM25+dense; free demo URL |
| Embeddings | voyage-finance-2 (primary) + bge-m3 (degraded fallback) | Domain-trained; 8-10% NDCG lift on financial corpora |
| Reranker | Cohere Rerank 3.5 (primary) + ms-marco-MiniLM (fallback) | Managed quality; ~150ms; <$0.001/query |
| Orchestration | LangGraph | Stateful DAG with conditional branching; per-node LangSmith tracing |
| Primary LLM | Claude Sonnet 4.6 (`claude-sonnet-4-6`) with prompt caching | Best for citation enforcement + structured tool use |
| Router LLM | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | 10× cheaper for 4-class intent classification |
| Structured outputs | Claude tool use + Pydantic schemas | Defensible; beats regex |
| Structured store | DuckDB | Columnar; 10-50× faster than Postgres/SQLite for OHLCV + fundamentals |
| Experiment tracking | MLflow | Ablation runs + parameter lineage |
| Evals | RAGAS + 10 pytest assertions | Industry standard; CI-gateable |
| Observability | LangSmith | Trace every node; failure-mode logging |
| Serving | FastAPI (async) + Docker Compose | Production standard |
| Demo UI | Streamlit | Free public URL; 5-tab multi-scenario |
| Deployment | Render (always-on) + Qdrant Cloud free tier | Live URL, zero recruiter friction |
| CI/CD | GitHub Actions with pytest + RAGAS gate | Fails if faithfulness < 0.75 |
| Load test | locust, 30 concurrent users | Enough to document P95 + bottleneck |

---

## 4. Scope lock — what's in the repo

```
finsight/
├── data/                        # DVC tracked, gitignored if >50MB
├── notebooks/                   # 01_eda, 02_chunking_eval, 03_conflict_calibration
├── src/
│   ├── ingestion/               # loader.py, schema.py (DuckDB), temporal_tagger.py
│   ├── indexing/                # qdrant_client.py, ingest_vectors.py, chunker.py (3 strategies)
│   ├── retrieval/
│   │   ├── graph.py             # LangGraph StateGraph (6 nodes)
│   │   ├── query_understanding.py
│   │   ├── router.py            # 4-path Haiku classifier
│   │   ├── retriever.py         # Qdrant hybrid + recency boost + Cohere rerank
│   │   ├── context_builder.py   # DuckDB JOIN + staleness check
│   │   └── degradation.py       # documented fallback chain
│   ├── generation/
│   │   ├── generator.py         # Sonnet streaming + prompt caching
│   │   ├── citation_parser.py
│   │   └── tool_schemas.py      # Pydantic schemas
│   ├── insight/
│   │   └── conflict_detector.py # 20+20 labeled pair calibration
│   ├── guardrails/
│   │   ├── input_guard.py       # Presidio PII + jailbreak check
│   │   └── output_guard.py      # faithfulness threshold
│   ├── recommendations/
│   │   └── related_tickers.py   # ticker centroids + nearest-neighbor
│   ├── evaluation/
│   │   ├── ragas_runner.py
│   │   ├── ablation.py          # 3 ablations: retrieval, chunking, reranker
│   │   ├── llm_compare.py       # Claude vs GPT-4o on golden set
│   │   └── golden_set.py        # 50 hand-curated queries incl. 5 adversarial + 5 abstention
│   └── utils/
│       ├── config.py
│       ├── cost_tracker.py
│       └── failure_tracker.py
├── api/
│   └── main.py                  # FastAPI async with /query, /feedback, /health, /recommend
├── ui/
│   └── streamlit_app.py         # 5 tabs (4 core + business value)
├── evals/
│   ├── golden_queries.jsonl     # 50 queries
│   ├── conflict_pairs.jsonl     # 20 known-conflict + 20 clean
│   └── results/
├── docs/
│   ├── PRD.md
│   ├── decisions.md             # 5+ engineering war stories
│   ├── architecture.md          # diagram + node descriptions
│   └── finsight_spec_v2.3.md    # this file
├── tests/                       # ~10 pytest assertions for CI
├── .github/workflows/eval.yml
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md                    # architecture diagram, ablation tables, live demo link
```

---

## 5. 5-week build plan

### Week 1: End-to-end skeleton + early deploy (15-20 hrs)
**Ship by end of week:** working live URL on Render, even if minimal. Starting with public deploy reduces deployment risk at the end.

- Day 1-2: repo structure, git + DVC, `docs/PRD.md` written, `.env.example`, Docker Compose (FastAPI + Qdrant)
- Day 3-4: ingest Motley Fool earnings transcripts (subset — top 100 tickers, not all 50K), fixed-size chunking, bge-m3 local embeddings → Qdrant
- Day 5: single dense-only retrieval → Claude Sonnet generation with structured citations tool use → FastAPI `/query`
- Day 6-7: Streamlit single query box + citations display, deploy to Render + Qdrant Cloud free tier, **get live URL working**

**Exit:** live URL returns cited answer in <10s. Share URL with 1 friend as smoke test.

### Week 2: Full retrieval pipeline (15-20 hrs)

- Day 1-2: switch embeddings to voyage-finance-2, enable Qdrant hybrid BM25+dense
- Day 3: add Cohere Rerank 3.5
- Day 4: ingest SEC fundamentals + OHLCV into DuckDB, add ticker JOIN in context builder
- Day 5: LangGraph 4-path router with Haiku + prompt caching
- Day 6: Query Understanding Node 1 (rewriter + decomposer)
- Day 7: temporal metadata + recency boost, LangSmith tracing, streaming

**Exit:** 4 routing paths work, streaming visible in UI, LangSmith trace shows all 6 nodes.

### Week 3: Insight layer + evals (15-20 hrs) — the differentiator week

- Day 1-2: **Evidence Conflict Detector** with 20+20 labeled pairs for calibration
- Day 3: conflict UI inline in Streamlit
- Day 4: build golden set (50 queries = 10 per path × 4 + 5 adversarial + 5 abstention)
- Day 5: RAGAS runner + 3 ablations (retrieval, chunking, reranker) — log to MLflow
- Day 6: Claude vs GPT-4o comparison on golden set
- Day 7: GitHub Actions RAGAS CI gate

**Exit:** 3 ablation tables with real numbers, conflict detector working on 3+ real examples, CI green.

### Week 4: Production polish + recommendation layer (15-20 hrs)

- Day 1: cost tracker + failure mode logger
- Day 2: thumbs up/down feedback endpoint, guardrails visible in UI
- Day 3: last-3-turn multi-turn context
- Day 4: related tickers recommendation (ticker centroids, nearest-neighbor), Streamlit sidebar
- Day 5: Streamlit 5-tab demo polish (Tab 1 Earnings, Tab 2 Metrics, Tab 3 **Conflict**, Tab 4 Price/News, Tab 5 Business Value)
- Day 6: locust load test at 30 concurrent, document P95 + bottleneck
- Day 7: pytest suite + ~10 assertions

**Exit:** all 5 demo tabs working, load test documented, failure modes visible in UI sidebar.

### Week 5: Demo + positioning (10-15 hrs) — the distribution week

- Day 1: **90-second Loom demo video** walking through all 5 tabs + conflict detector moment
- Day 2: README polish (architecture diagram, 3 ablation tables, live demo link, quickstart)
- Day 3: `docs/decisions.md` with 5+ war stories (licensing pivot, Cohere outage design, conflict calibration, cost routing, degraded mode)
- Day 4: first technical blog post published ("How I built an evidence conflict detector for financial RAG — with numbers")
- Day 5: LinkedIn Featured section update (live URL + video + blog post)
- Day 6-7: buffer / polish / fix issues surfaced from friend testing

**Exit:** ready to interview. URL live, video on LinkedIn, blog post published, README lands in 30 seconds.

---

## 6. Definition of Done (20 items, not 45)

- [ ] Live Render URL works without setup
- [ ] README passes 30-second scan (architecture diagram + 3 ablation tables + demo link + quickstart)
- [ ] 90-second Loom demo video on LinkedIn Featured section
- [ ] At least 1 technical blog post published (LinkedIn or Medium)
- [ ] Retrieval ablation: hybrid+rerank beats dense-only by ≥10% NDCG
- [ ] Chunking ablation: 3-way comparison in README
- [ ] Reranker ablation: no-rerank vs Cohere in README
- [ ] Claude vs GPT-4o faithfulness comparison in README
- [ ] RAGAS faithfulness ≥ 0.75 on 50-query golden set (stretch: 0.80)
- [ ] P95 latency ≤ 3s documented from 30-user locust load test
- [ ] Cost ≤ $0.005/query documented and visible in UI metrics sidebar
- [ ] All 4 routing paths demonstrated in Streamlit tabs
- [ ] Evidence Conflict Detector working in Tab 3 with 3+ real examples
- [ ] Related tickers recommendation working in sidebar
- [ ] Guardrails visible in UI (grounded / flagged / refused / stale)
- [ ] Streaming output visible in Streamlit
- [ ] Thumbs up/down feedback logging working
- [ ] GitHub Actions RAGAS CI gate green on main
- [ ] `docs/PRD.md` + `docs/decisions.md` (5+ war stories) + `docs/architecture.md` complete
- [ ] All 10 v2.2 interview decision questions answerable cold, without notes

---

## 7. The 5 interview moments this enables

When an interviewer asks about FinSight, you control the conversation toward one of these:

1. **"Let me show you the live demo"** — Tab 3 (conflict detector) with a real example
2. **"The architecture is a 6-node LangGraph DAG"** — whiteboard sketch from `docs/architecture.md`
3. **"Here's the ablation: hybrid+rerank beats dense-only by X% NDCG at $Y/query"** — real number
4. **"Cost routing reduces spend 55% by using Haiku for intent + Sonnet only for synthesis, with prompt caching at 80%+ hit rate"** — production-thinking signal
5. **"Retrieval and recommendation are the same problem — I reused the Qdrant embeddings for related-ticker recs on shared infrastructure"** — architecture-thinking signal

Every one of those moments is in v2.3. Anything that doesn't drive one of them was cut.

---

## 8. What's explicitly in "future work" in the README

These get one line each in the README's Future Work section — proof of awareness without scope creep:

- DeepEval + 3-LLM consensus judge for agreement measurement
- BEIR FiQA-2018 generalization benchmark
- Arize Phoenix embedding cluster viz
- Two-tower bi-encoder fine-tuning on Motley Fool Q&A pairs (unified retrieval + recommendation backbone)
- Related queries + personalized doc feed
- Semantic chunking ablation
- Int8 Qdrant quantization
- Human eval with Cohen's kappa
- Pareto cost×quality frontier
- Llama 3.1 8B local deployment via Ollama

Interviewers asking "did you consider X?" get: "Yes, it's in the Future Work section. I didn't ship it because [reason]." That's a better answer than shipping everything poorly.

---

## 9. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Week-by-week overruns (most likely failure mode) | Weekly cut decisions every Sunday: what ships vs what moves to "future work" |
| Motley Fool Kaggle licensing ambiguity | Use 10-K subset + SEC earnings call transcripts only if licensing unclear |
| Qdrant Cloud 1GB limit | Subset to top 100 tickers × last 2 years; document limitation |
| yfinance TOS | Use Stooq.com for OHLCV if yfinance is risky for public demo |
| Voyage/Cohere API cost overrun during eval | Budget cap at $100 total; run full eval only once at end |
| Render cold-start on free tier | Upgrade to $7/mo plan 1 week before interviewing (worth it) |

---

## 10. When to start interviewing

**Week 3 Day 7** (conflict detector working, ablations in hand) = you can pass architecture interviews.
**Week 5 Day 7** (video + blog + decisions.md) = you pass everything and the URL makes recruiters respond 3× faster.

Apply to Tier 1A companies in Week 4. First recruiter screens line up for Week 5-6. By the time you hit onsites in Week 7-8, FinSight is done and you're talking through real results, not plans.

---

**End of v2.3 spec.** Canonical. Any conflict with v2.2 or earlier: this document wins. If in doubt: cut more, ship more.
