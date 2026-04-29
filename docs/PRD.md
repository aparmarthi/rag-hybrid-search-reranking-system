# FinSight — Product Requirements Document

**Owner:** Amey Parmarthi
**Status:** In development (Week 1 of 5)
**Last updated:** 2026-04-29
**Canonical spec:** `docs/finsight_spec_v2.3.md`

---

## 1. Problem

Equity research is bottlenecked by manual evidence gathering. Analysts spend 3–4 hours per company report cross-referencing three disconnected sources of truth:

- **Earnings call transcripts** (what management said)
- **SEC filings** (what the company formally disclosed)
- **Market data** (how the stock reacted)

When those sources disagree — management guidance vs filed numbers, Q2 guidance vs Q3 guidance, transcript revenue vs XBRL revenue — there is no systematic way to surface the conflict. Today's workflow relies on an analyst manually spotting the delta. That workflow fails at scale (500+ companies per analyst watchlist) and fails consistently under time pressure (earnings season).

The downstream cost: research outputs built on inconsistent evidence, missed red flags in regulatory filings, and analyst productivity capped at what a human can cross-reference by hand.

## 2. Target user

**Primary:** Institutional equity analyst at a fund with < $1B AUM.
- Can't afford Bloomberg Terminal ($24K/seat) or AlphaSense ($15K/seat)
- Covers 50–500 tickers with 1–3 junior analysts supporting
- Produces 10–30 written research reports per quarter
- Needs cited, defensible evidence in every research output
- Time-boxed under earnings season (4 weeks × 4 quarters = their entire year)

**Secondary:** Retail investor doing deep due diligence before a position.

**Not building for:** day traders, algorithmic quant systems, general-purpose financial chatbots, crypto speculation, real-time market data consumers.

## 3. North Star metric

```
Faithfulness ≥ 0.80 (RAGAS) at P95 latency ≤ 3s and cost ≤ $0.005/query
```

All three conditions must hold. Each alone is not sufficient:
- Faithful but slow = unusable during earnings hour
- Fast but not faithful = worse than the status quo (manual research)
- Fast and faithful but expensive = can't scale to 500-ticker watchlists

## 4. Guardrail metrics

| Metric | Target | Why |
|---|---|---|
| Hallucination rate | < 5% | Legal liability under SEC Rule 10b-5 |
| Out-of-scope refusal rate | > 90% | Avoid "should I buy NVDA?" drift |
| Context precision | ≥ 0.75 | Retrieved chunks must be genuinely relevant |
| Temporal staleness rate | < 10% | Financial data is time-sensitive |
| Citation precision | ≥ 0.90 | Every numeric claim traceable to source |
| Abstention accuracy | ≥ 0.85 | Knows when it doesn't know |

## 5. Success criteria (Definition of Done)

FinSight v2.3 is ready to present in interviews when:

1. **End-to-end query returns cited answer in under 3 seconds** on live Render URL
2. **Ablation shows hybrid + rerank beats dense-only by ≥ 10% NDCG** on 50-query golden set
3. **Conflict detector catches ≥ 80% of known conflicts** with < 10% false positive rate on 20+20 labeled pairs
4. **Related-ticker recommendations achieve ≥ 0.60 precision@5** against analyst-labeled peer set (optional — cut if Week 4 runs late)

Full 20-item DoD in `docs/finsight_spec_v2.3.md`.

## 6. Key trade-offs (and why)

| Chose | Over | Why |
|---|---|---|
| voyage-finance-2 | OpenAI text-embedding-3-large | Domain-specific pretraining on SEC + earnings corpora closes ~8-10% NDCG gap on financial retrieval |
| Cohere Rerank 3.5 | Self-hosted cross-encoder | Managed API removes GPU infrastructure and variability; cost < $0.001/query is worth ~150ms latency |
| LangGraph | Vanilla LangChain LCEL | 6 nodes with conditional branching and stateful fan-out is a DAG, not a chain |
| Recency boost (+0.15 for last 2Q) | Pure relevance ranking | Financial data is time-sensitive; 2022 earnings are rarely relevant to 2024 questions |
| Structured tool-use citations | Regex parsing | Claude-enforced Pydantic schemas are defensible in production; regex rots |
| Haiku-then-Sonnet cost routing | Sonnet on every query | Intent classification is a 4-class problem — Haiku is 10× cheaper with < 100ms added latency |
| Prompt caching | Fresh every call | 60–80% cost reduction on static system prompt + tool definitions; essential at $0.005/query target |
| Qdrant | Pinecone / FAISS | Native hybrid BM25+dense in one index; free 1GB cloud tier; fastest metadata filtering |
| 4-path router (earnings / metrics / price / news) | Monolithic retrieval | Per-source Recall@K story is an interview artifact worth the complexity |
| Evidence conflict detector | Answer-only RAG | Turns a Q&A tool into a product; the #1 interview moment |

## 7. NOT building

- Real-time trading signals
- Portfolio management / position sizing
- General-purpose chatbot
- Buy/sell recommendations (guardrail-blocked)
- Anything outside the public financial-filings / earnings / OHLCV domain
- Crypto, commodities, private markets

## 8. User journeys

### Journey 1 — Earnings analysis (primary)
An analyst covering AAPL gets a new Q3 2024 earnings call transcript. They type:
> "What did Apple say about iPhone margins in Q3 2024?"

FinSight returns:
- A 2-3 paragraph answer with every numeric claim cited to `[Transcript: Apple Q3 2024 @ 23:14]`
- The relevant earnings call chunks in a sidebar
- Fundamentals row: Q3 2024 iPhone revenue from 10-Q
- Guardrail indicators: grounded ✓, no PII, no financial advice intent
- Routing path shown: `earnings_analysis`

### Journey 2 — Evidence conflict (the differentiator)
Analyst asks:
> "Did Nvidia Q3 guidance match Q2 guidance?"

FinSight returns:
- Direct comparison answer
- **Conflict panel:** "⚠️ Sources disagree: Q2 call guided 15% y/y growth [Transcript: NVDA Q2 2024]; Q3 10-Q reported 12% y/y [SEC 10-Q 2024-Q3]. Delta 3pp, above 1pp threshold."
- Links to both source chunks

### Journey 3 — Financial metrics (structured)
> "Microsoft revenue and EPS trend last 4 quarters"

Returns tabular answer from DuckDB fundamentals JOIN, cited to filings.

### Journey 4 — Price + news context
> "What drove Tesla stock movement in October 2024?"

Returns OHLCV event-window chart + news chunks from that window, explained.

## 9. User experience principles

1. **Every numeric claim cites its source.** Non-negotiable.
2. **Uncertainty is visible.** Conflict panels, staleness warnings, and degraded-mode banners are features, not failures.
3. **Streaming matters.** First token in < 500ms makes 3s P95 feel fast.
4. **Failure modes are observable.** 5-category failure logger (retrieval_miss / bad_ranking / hallucination / ambiguous_query / stale_data) visible in sidebar.
5. **Cost is visible.** Every query shows $/query in metrics sidebar.

## 10. Business model (for product_strategy discussion — summary)

- **Pricing:** $500/mo per seat (2.5% of Bloomberg)
- **ICP:** Small L/S hedge funds $100M–$1B AUM
- **WTP:** 3 hrs/day saved × $200/hr × 20 days = $12K/month value → 24x ROI at $500
- **Unit economics:** $0.005/query × 50 queries/day × 20 days = ~$5/month cost → ~99% gross margin
- **Moat:** Fine-tuned domain encoder + query log data flywheel + eval harness IP

Full version will live in `docs/product_strategy.md` (written in Week 5 as part of interview artifacts).

## 11. Competitive landscape

| Competitor | Price | Hybrid retrieval | Conflict detection | Open eval |
|---|---|---|---|---|
| Bloomberg Terminal | $24K/yr | — | — | — |
| AlphaSense | $15K/yr | Proprietary | — | — |
| Hebbia | Enterprise | Yes | — | — |
| BamSEC | Low $ | Keyword only | — | — |
| FactSet | $$$$ | — | — | — |
| **FinSight** | $500/mo | **Yes** | **Yes** | **Yes** |

## 12. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Hallucination liability (SEC Rule 10b-5) | High | Aggressive faithfulness gate + explicit "not investment advice" disclaimer |
| Data licensing (Motley Fool on Kaggle) | Medium | SEC-only fallback mode documented in decisions.md |
| yfinance TOS (Yahoo redistribution) | Medium | Stooq.com fallback OR static dataset snapshot for demo |
| Qdrant Cloud 1GB limit | Low | Subset to top 100 tickers × last 2 years |
| API cost overrun during eval | Medium | $100 total budget, full eval runs once at end of Week 3 |
| Scope creep vs 5-week timeline | High | Weekly Sunday cut decisions: what ships vs what moves to Future Work |

## 13. Out-of-scope (Future Work — mentioned in README for interview awareness)

- Two-tower bi-encoder fine-tuning on Motley Fool Q&A pairs (Phase 6 stretch)
- BEIR FiQA-2018 generalization benchmark
- 3-LLM consensus judge (Claude + GPT + Gemini)
- Arize Phoenix embedding cluster visualization
- DeepEval as second eval framework
- Semantic chunking (SemanticChunker)
- Int8 quantization on Qdrant
- Related queries + personalized doc feed (v2.3 keeps only related tickers)
- 10-K graph edges for competitor identification
- Local Llama 3.1 8B deployment via Ollama
- Cohen's kappa human evaluation with inter-annotator agreement
- Adversarial suite as separate module (folded into golden set)
- Multi-turn conversation memory compression

## 14. Changelog

- **2026-04-29:** Initial PRD committed. Scoped to v2.3 (5-week interview-ready plan).
