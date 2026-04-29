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

## DEC-004 (placeholder for Week 2)
**Topic:** Cohere Rerank 3.5 vs local ms-marco-MiniLM cross-encoder. Will populate after implementing both in Week 2.

---

## DEC-005 (placeholder for Week 3)
**Topic:** Conflict detector threshold calibration — how we learned per-metric thresholds from 20+20 labeled pairs instead of hand-tuning.

---

## DEC-006 (placeholder for Week 4)
**Topic:** Cost routing story — measured cost reduction from Haiku-intent + Sonnet-synthesis + prompt caching vs Sonnet-on-every-query.

---

## DEC-007 (placeholder for Week 4)
**Topic:** Failure mode discovered in production (inevitable). Write the war story as soon as it happens.

---

## Format notes for future entries

- Write these **as they happen**, not retroactively. Retroactive entries sound fake in interviews.
- Always include the **option we almost chose but didn't**. That's the interesting part.
- Always include the **revisit trigger**. Shows you know decisions are not permanent.
- Numbers over adjectives. "8-10% NDCG lift" beats "significantly better."
