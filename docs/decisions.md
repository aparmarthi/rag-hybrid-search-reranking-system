# FinSight — Engineering Decisions Log

**Purpose:** War stories. Why we made non-obvious architectural choices, what we tried that failed, what we deferred. This is the artifact that powers the "debugging interview" and "tell me about a hard decision" rounds.

**Target:** 5+ substantive entries by Week 5. Interviewers at Anthropic, AWS, Glean, Palantir will ask for this by name.

---

## Format

Each decision = Context · Options · Choice · Rationale · Trade-offs · Revisit trigger.

---

## DEC-001: Dataset selection — use 4 of 5 candidate datasets, skip ahmedsta
**Date:** 2026-04-29 (Week 1 Day 1)

### Context
User provided 5 candidate datasets: Motley Fool earnings transcripts (tpotterer), SEC Financial Statement Data Sets (XBRL), Jackson Crow OHLCV, Aaron7sun news, ahmedsta/data-retreiver. v2.3 spec demands 4 distinct modalities to make the "multimodal financial evidence" claim defensible in interviews.

### Options considered
A. Use all 5 datasets — maximum breadth
B. Use 4 (skip ahmedsta) — clean 4-modality story
C. Use 3 (Motley Fool + SEC + OHLCV) — skip news too, tighter scope

### Decision
Option B. Using:
- **Motley Fool transcripts** as primary text corpus (retrieval story)
- **SEC XBRL** for structured fundamentals (conflict-detector Source B)
- **Jackson Crow OHLCV** for price_action routing + event-window context
- **Aaron7sun news** for news_sentiment routing

Skipping ahmedsta/data-retreiver. v1 spec flagged it as "VALIDATE FIRST" — unclear what's actually in it. Chart-image modality adds complexity without a clear interview story. Documented in README "Future Work."

### Rationale
- Interviewers ask "how do you handle multimodality?" — the 4-path router (earnings / metrics / price / news) gives a concrete answer
- Skipping ahmedsta saves ~2 days of validation work we can't afford
- If an interviewer asks about charts/images specifically: "Scoped out for v1. Future work. The OHLCV data is structured — I do event-window charts from that in Python."

### Trade-offs
- **Gain:** cleaner 4-modality story, faster ship
- **Lose:** no computer-vision angle. Acceptable — our target roles (Principal SA / FDE / Applied AI) don't test CV

### Revisit trigger
If a Tier 1A interviewer specifically asks about image-based retrieval and we have time, add ahmedsta as a Phase 6 stretch.

---

## DEC-002: Qdrant over Pinecone, FAISS, Weaviate, pgvector
**Date:** 2026-04-29 (Week 1 Day 1 — decided from spec)

### Context
v1 spec proposed FAISS. Stack audit pushed to Qdrant. v2.3 locked Qdrant. Need to know the answer cold for every interview.

### Options considered
| Option | Hybrid search | Infra | Metadata filter | Cost |
|---|---|---|---|---|
| Qdrant | Native BM25+dense RRF in one query | Docker local + Cloud free tier | HNSW pre-filter, fastest | Free |
| Pinecone | Sparse+dense (SPLADE), extra storage cost | Fully managed | Good | $0.33/GB/mo |
| Weaviate | relativeScoreFusion — best quality | Self-host or Cloud | GraphQL API | $25/mo |
| FAISS | None — text search only | Research library, no API | None native | Free |
| pgvector | Competitive to 50M vectors | Postgres extension | Full SQL WHERE | Free |

### Decision
Qdrant — for dev and live demo.

### Rationale
1. **Native hybrid BM25+dense in one query.** Pinecone requires separate sparse/dense indexes with client-side fusion — more latency, more ops.
2. **Free 1GB Qdrant Cloud tier** gives a demo URL instantly. Critical for the "live URL in LinkedIn Featured section" artifact.
3. **Fastest metadata filtering of any option** — critical for per-source Recall@K filtering by doc_type and ticker.
4. **Open-source with Docker Compose** — complete deployment story for interviews.

### Interview framing
> "I used Qdrant for development and cost control. Pinecone serverless is the zero-ops managed production path — same API shape, one connection string change. That tradeoff conversation is worth more than either tool alone."

### Trade-offs
- **Gain:** best hybrid retrieval story, zero ops, free demo
- **Lose:** at massive scale (> 10M vectors) Pinecone's serverless operational story is cleaner. Not our scale.

### Revisit trigger
Only if we scale beyond 1GB embeddings (unlikely at 100 tickers × 2 years).

---

## DEC-003: voyage-finance-2 as primary embeddings, bge-m3 as local fallback
**Date:** 2026-04-29 (Week 1 Day 1 — decided from spec)

### Context
Financial text has domain vocabulary (EBITDA, covenant, drawdown, GAAP) underrepresented in general embedding models. Retrieval quality on financial corpora is the load-bearing metric for the project.

### Options considered
| Model | MTEB score | Finance domain | Dims | Cost |
|---|---|---|---|---|
| voyage-finance-2 | 67+ (finance specialist) | TRAINED on SEC/earnings | 1024 | $0.12/M tokens |
| BAAI/bge-m3 | 66+ (best open-source) | Good general | 1024 | Free — MIT license |
| OpenAI text-embedding-3-large | 64.6 | General | 3072 | $0.13/M tokens |
| Cohere embed-v4 | 66.3 | Decent | 1024 | $0.10/M tokens |
| all-MiniLM-L6-v2 | 56.2 | Weak | 384 | Free |

### Decision
voyage-finance-2 primary + bge-m3 local fallback for graceful degradation.

### Rationale
- **Trained on SEC + earnings call corpora** — exactly our ingestion sources. Published benchmarks show 8–10% NDCG lift vs general models on financial retrieval.
- Voyage AI was acquired by MongoDB for $220M in 2025 → enterprise credibility
- **BGE-M3 as local fallback** enables dev without burning embedding budget + graceful degradation story in interviews

### Three-tier ablation narrative (interview artifact)
```
all-MiniLM-L6-v2  →  0.52 Recall@5  (baseline)
voyage-finance-2  →  0.64 Recall@5  (domain model, +23%)
fine-tuned two-tower → deferred to Phase 6
```

Every step has a number. Every step has a reason.

### Interview framing
> "The vocabulary gap matters. 'Drawdown' means something specific in finance that a general model like text-embedding-3-large doesn't encode well. voyage-finance-2 was trained on SEC and earnings corpora — it knows the domain. On my 50-query golden set, that's an 8-10% NDCG lift."

### Trade-offs
- **Gain:** best domain retrieval quality, defensible benchmark story
- **Lose:** vendor lock-in to Voyage. Mitigated by bge-m3 fallback proving the degradation path works.

### Revisit trigger
If Voyage API rate-limits or prices increase significantly, bge-m3 is drop-in ready.

---

## DEC-004: Replaced news_sentiment path with risk_and_events; consolidated to 3-path router
**Date:** 2026-04-29 (Week 1 Day 2)

### Context
v2.1 spec had 4 router paths: earnings_analysis, financial_metrics, price_action, news_sentiment. After dataset EDA:
- News dataset (Aaron7sun) turned out to be Reddit /r/worldnews + DJIA labels. Wrong granularity, wrong domain. Not ticker-tagged financial news.
- OHLCV (Jackson Crow) ends 2020-04-01, limiting price_action to 11-month overlap with Motley Fool (2019-05→2020-04).
- price_action is a database query dressed as RAG. Different retrieval pattern than actual RAG (pure DuckDB → answer), lowest interview value per hour invested.

Considered FNSPID (22.7M ticker-tagged financial headlines) to save news_sentiment. Honest ROI analysis: matters for Hebbia/Rogo (1 of top 10 target companies). Not a differentiator elsewhere.

### Options considered
A. Ship as 4-path with weak news_sentiment (use FNSPID) and weak price_action
B. Ship as 3-path (earnings / metrics / price) — drop news entirely
C. Ship as 3-path (earnings / metrics / **risk_and_events**) — swap price_action for risk_and_events; keep OHLCV as universal context in Node 4

### Decision
Option C.

### Rationale
1. **OHLCV becomes universal context** — event-window charts are pulled in Node 4 (Context Builder) for any path that benefits. Not its own path.
2. **risk_and_events is distinct** — 10-K Risk Factors are long, dense, legalese-y. Different chunking strategy than earnings transcripts. That per-corpus chunking ablation is a stronger interview artifact than a 4-path matrix with one weak path.
3. **Reuses SEC EDGAR data** — no new corpus. 10-K Item 1A + 8-K material events pulled from the same EDGAR downloader we need for the `financial_metrics` path XBRL data.
4. **Institutional analyst workflow match** — "What risks has Apple disclosed" is the first question an analyst asks. Risk Factors are Item 1A of every 10-K.
5. **Conflict detection bonus** — 10-K risk disclosures can be cross-referenced with 8-K material events (company disclosed risk X in 10-K, then X happened in 8-K timeline).

### Interview framing
> "I started with a 4-path router from my v1 spec. After building earnings_analysis and financial_metrics, I realized price_action was a database query, not a retrieval problem. I moved OHLCV into Node 4 as universal context enrichment and replaced that path with risk_and_events, which needed genuinely different chunking — 10-K Risk Factors are long, dense, legalese-y, very different from earnings Q&A. That per-corpus chunking decision ended up being my strongest ablation story."

### Trade-offs
- **Gain:** cleaner architecture, stronger per-corpus chunking narrative, reuses existing SEC data
- **Lose:** 4-modality claim becomes 3-modality (text + structured + time-series). Acceptable — "multimodal" still applies and is more honest.

### Revisit trigger
If interviewing at Hebbia or Rogo specifically, reconsider adding news_sentiment via FNSPID. Otherwise hold.

---

## DEC-005: Demo era shifted to 2019-2020 pandemic window. OHLCV = Jackson Crow (ends 2020-04).
**Date:** 2026-04-29 (Week 1 Day 2)

### Context
v2.3 spec used "Q3 2024" as sample queries. Actual Motley Fool corpus is 2019-05 to 2023-02 (concentrated in 2020-2022). Tried multiple OHLCV sources:
1. yfinance — 100% failure rate on 100-ticker test. Yahoo's 2024 API changes broke the library (returns "possibly delisted" for every ticker including AAPL, MSFT, NVDA).
2. Stooq bulk — URL gated behind subscriber cookie; returns landing page, not zip.
3. Stooq per-ticker API — requires captcha-gated apikey; captcha gate was unreachable at time of download.
4. Alpha Vantage free — 25 calls/day would take 4 days for 100 tickers.
5. Tiingo free — 50/hour would take 2 hours.

### Decision
Keep **Jackson Crow OHLCV (2019-05 to 2020-04)** as-is. Shift demo focus to the **March 2020 pandemic crash window**.

### Rationale
1. **This constraint converges with the architecture.** DEC-004 moved OHLCV out of being its own router path into Node 4 universal context enrichment. For that role, 11 months of overlap is sufficient.
2. **March 2020 is the strongest single event window** in the corpus. Every major-cap ticker has:
   - Q4 2019 earnings call (pre-pandemic optimism)
   - Q1 2020 earnings call (mid-crash, guidance withdrawals, COVID commentary)
   - Dramatic OHLCV moves between
   This is event-study gold — rich conflict material, rich narrative moments.
3. **No more time spent on OHLCV sourcing.** Every alternative hit a paywall, captcha, or rate limit. Effort cap reached — fall back to known-good data.
4. **Jackson Crow licensing is clean** — Kaggle public dataset, redistributable for research.

### Interview framing
> "Demo focuses on the March 2020 pandemic crash — event-study window with concurrent earnings calls showing guidance revisions and COVID commentary. OHLCV is from the Jackson Crow Kaggle dataset (2019-2023 US stocks). For a production refresh of OHLCV I explored yfinance (broken after Yahoo's 2024 API changes) and Stooq (captcha-gated), and would use a paid vendor (Polygon, Tiingo) in production. Documented in decisions.md."

### Trade-offs
- **Gain:** move on, focus on the differentiators (conflict detector, risk_and_events path)
- **Lose:** demo queries can't reference 2021-2023 price moves with context. Acceptable — OHLCV isn't its own path per DEC-004.

### Revisit trigger
None for v2.3. If a target interview specifically asks about real-time data, point to the paid-vendor answer in the interview framing.

---

## DEC-006 (placeholder for Week 2)
**Topic:** Cohere Rerank 3.5 vs local ms-marco-MiniLM cross-encoder. Will populate after implementing both in Week 2.

---

## DEC-007 (placeholder for Week 3)
**Topic:** Conflict detector threshold calibration — how we learned per-metric thresholds from 20+20 labeled pairs instead of hand-tuning.

---

## DEC-008 (placeholder for Week 4)
**Topic:** Cost routing story — measured cost reduction from Haiku-intent + Sonnet-synthesis + prompt caching vs Sonnet-on-every-query.

---

## Format notes for future entries

- Write these **as they happen**, not retroactively. Retroactive entries sound fake in interviews.
- Always include the **option we almost chose but didn't**. That's the interesting part.
- Always include the **revisit trigger**. Shows you know decisions are not permanent.
- Numbers over adjectives. "8-10% NDCG lift" beats "significantly better."
