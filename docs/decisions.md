# FinSight — Engineering Decisions Log

**Purpose:** War stories. Why we made non-obvious architectural choices, what we tried that failed, what we deferred. This is the artifact that powers the "debugging interview" and "tell me about a hard decision" rounds.

**Target:** 5+ substantive entries by Week 5. Interviewers at Anthropic, AWS, Glean, Palantir will ask for this by name.

---

## Format

Each decision = Context · Options · Choice · Rationale · Trade-offs · Revisit trigger.

---

## DEC-001: Dataset selection — use 4 of 5 candidate datasets, skip ahmedsta
**Date:** 2026-04-29 (Week 1 Day 1)

> **Later superseded in part:** this entry reflects the original 4-path plan
> (earnings / metrics / price_action / news_sentiment). **DEC-004** consolidated
> to the 3-path router (earnings_analysis / financial_metrics / risk_and_events)
> after dataset review. Kept as-written to preserve the decision trail — read
> DEC-001 → DEC-004 in sequence for the evolution.

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

## DEC-006: Cohere Rerank 3.5 primary + local ms-marco cross-encoder fallback
**Date:** 2026-07-12 (Week 2)

### Context
Stage 2 of retrieval: after hybrid BM25+dense fetches a candidate pool (recall-oriented), a cross-encoder re-scores each candidate against the query jointly (precision-oriented) and reorders the top-k. Two viable rerankers: Cohere's managed Rerank API, or a self-hosted cross-encoder.

### Options considered
| Option | Quality | Latency | Ops | Cost |
|---|---|---|---|---|
| Cohere Rerank 3.5 (`rerank-v3.5`) | Strong, managed | ~150ms | Zero (API) | <$0.001/query |
| ms-marco-MiniLM-L-6-v2 (local cross-encoder) | Good | CPU-bound, slower | Model in process (~90MB) | Free |

### Decision
Cohere `rerank-v3.5` primary; ms-marco-MiniLM-L-6-v2 as an automatic fallback. `reranker.py` catches ANY Cohere error and degrades to the local cross-encoder rather than failing the query; a further failure falls back to raw retrieval order. Config `reranker_backend` also offers `none` (pass-through) for the ablation baseline.

### Rationale
1. **Managed quality, zero GPU ops** — reranking is where a cross-encoder's joint query-doc scoring adds precision the bi-encoder retrieval can't. Cohere delivers that without hosting a model in the 512MB free-tier serve process.
2. **Deploy-friendly** — Cohere is an API call; no model in the web dyno (same reason we chose Voyage for embeddings).
3. **The fallback is the resilience story** — "Cohere outage → local cross-encoder → raw order" is a graceful-degradation chain I can point to in interviews, and it's tested (it fired live during the model-name bug below and reranked correctly).

### The model-name gotcha (a real debugging note)
The v2.3 spec named the model `rerank-english-v3.5`. That returns **404 model not found** — Cohere dropped the `-english` suffix (v3.5 is multilingual). The correct ID is **`rerank-v3.5`**. I discovered this by probing the API for candidate names rather than guessing, and also confirmed **no Rerank 4 exists yet** (all `rerank-v4.0` variants 404). A stale `COHERE_RERANK_MODEL` in `.env` masked the fix at first — the env var overrode the corrected code default. Lesson: verify model IDs against the live API, and check `.env` overrides when a config change "doesn't take."

### Trade-offs
- **Gain:** best rerank quality with no GPU ops; free-tier-deployable; a real degradation chain.
- **Lose:** per-query Cohere dependency (mitigated by the local fallback) and a tiny cost (<$0.001/query).

### Revisit trigger
Week 3 ablation quantifies the rerank lift (no-rerank vs Cohere vs local). If Cohere's lift over the local cross-encoder is marginal, reconsider going local-only to drop the dependency. Adopt Rerank 4 when/if it ships (one-line config change).

---

## DEC-007: Evidence Conflict Detector — intra-transcript, precision-gated, intent-gated
**Date:** 2026-07-12 (Week 3)

### Context
The differentiator: surface contradictory numeric claims in the evidence instead
of blending them into one confident answer. The spec's canonical design compares
a transcript claim (Source A) vs an SEC XBRL filing (Source B). **Source B isn't
available** — only HTML filings were downloaded (no XBRL numbers), and the
`fundamentals` table is empty. So Week 3 builds the **intra-transcript** version:
guidance-vs-actual and cross-quarter drift within the transcript corpus. Same
engine; cross-source is later just "add SEC numbers to the claim set."

### Engine (two steps, source-agnostic)
1. **Extract** — one Sonnet structured-tool call over the evidence emits
   `NumericClaim`s (metric, **subject**, value, unit, period, is_guidance, chunk,
   quote). LLM extraction beats regex for numbers-in-prose.
2. **Compare** — pairwise, flag divergence beyond a per-metric threshold
   (revenue >3%, EPS >5%, margin >1pp, growth/guidance >2pp).

### The precision story (this is the interview-worthy part)
Naive comparison produced **false positives**; each gate below removed a class,
learned by inspecting real output rather than hand-waving:
- **Guidance ranges** ("down 15% to down 18%") → two claims from the SAME chunk.
  Gate: both claims must come from **different chunks**.
- **Quarter vs full-year** (Q3 18.5% vs FY 21%) → not a contradiction, different
  scope. Gate: **comparable periods** (same period, or guidance→actual for it).
- **Different segments** (Products +8% vs Services +17%, same call) → same metric
  label, different thing. Gate: added a **`subject`** field; require subject match.
- **Same-call figures** → a real conflict is guidance in one call vs actual in a
  **later** call. Gate: the two chunks must be from **different dates**.

Verified: a constructed genuine conflict (NVDA guided 15% for Q3, delivered 9%)
**fires** correctly; a control (data-center 15% vs gaming 9%, different subjects)
**does not**. Zero false positives across the earlier noisy queries after gating.

### Intent gating (latency)
The extraction call adds ~14-20s. Most queries have no conflict to find, so the
node only runs when the query is comparison/guidance-oriented (keyword gate:
"guidance", "versus", "match", "revised", …). Plain queries skip it (0ms);
comparison queries pay the cost for the differentiator. No extra LLM call to decide.

*Note (2026-10-16):* measured live, the extraction took **23.8–25.3s** (n=3, `evals/results/live_measurements_20261016T045744Z.json`), above the 14–20s estimate. The gate reads the Haiku-*rewritten* query, not the user's text, so it is only as stable as the rewrite. The Tesla Shanghai-vs-Fremont question ran the node on `/query` (rewrite: "…compared to Fremont factory…", which hits `compare`). Minutes later, a `/query/stream` run of the same question reached first token in 3.6s, too fast for a 25s extraction, so the gate was almost certainly off. That is inferred from timing; the measurement script didn't record the stream's per-node latencies. Not changed yet: gating on the raw query (or on raw OR rewritten) would make it deterministic.

### Honest limitation — the retrieval-pairing gap
The detector is correct, but **standard retrieval doesn't reliably fetch both
halves of a conflict pair** (a ticker's guidance chunk AND its later-actual chunk)
into the same result set — so live queries surface conflicts less often than the
engine can detect. The engine is proven on paired evidence; a conflict-oriented
retrieval mode (deliberately fetch a ticker's guidance + subsequent actuals) is
the follow-on. Documented rather than hidden — better to say "the detector is
right; the retrieval that feeds it needs a conflict-aware mode" than to fake it.

### Trade-offs
- **Gain:** a real, precision-first conflict detector with a genuine "here's how I
  killed each false-positive class" debugging narrative — stronger than a detector
  that fires often but cries wolf.
- **Lose:** cross-source (transcript vs filing) deferred; live recall limited by the
  retrieval-pairing gap.

### Revisit trigger
(1) Ingest SEC XBRL → cross-source conflicts. (2) Add conflict-oriented retrieval
so live queries reliably surface both halves. (3) Week-3 calibration: the spec's
20+20 labeled-pair threshold tuning, once a labeled set exists.

---

## DEC-008 (placeholder for Week 4)
**Topic:** Cost routing story — measured cost reduction from Haiku-intent + Sonnet-synthesis + prompt caching vs Sonnet-on-every-query.

**Week 1 note (2026-06-23):** Prompt caching is wired (a `cache_control` breakpoint on the system prompt in `generator.py`), but measured `cache_read=0` in Week 1 — the Week-1 system prompt (~350 tokens) is **below Sonnet 4.6's 2048-token minimum cacheable prefix**, so Anthropic silently declines to cache it. Deliberately NOT padding the prompt to cross the threshold (that would game the metric). The real cache win lands in Week 2 when the LangGraph system prompt (router instructions + few-shot + per-path context) clears 2048 naturally. Honest interview framing: "caching is architected in from day one; it starts paying off once the prompt is large enough to cache, which is the Week-2 pipeline — I didn't inflate the prompt just to show a cache hit."

---

## DEC-010: Anthropic API accessed directly for the generation core; OpenRouter reserved for the multi-model eval
**Date:** 2026-06-23 (Week 1 Day 5 — first live generation wiring)

### Context
Wiring the generator surfaced two environment problems on the dev machine: (1) an ambient `ANTHROPIC_BASE_URL` pointing at a corporate model-gateway proxy (with its own CA bundle) was intercepting the SDK's calls and failing TLS verification under Homebrew Python; (2) the personal Anthropic key had a $0 credit balance. Available credit was OpenAI ($22), OpenRouter ($10), and Google Cloud/Gemini ($300). The question: power FinSight's generation core through OpenRouter (existing credit, easy model-swapping) or add a small direct Anthropic top-up.

### Options considered
A. **OpenRouter for the generation core** — use existing $10, one OpenAI-compatible endpoint, trivial model-swapping across providers.
B. **Gemini for the generation core** — largest runway ($300), but a full rewrite and off-narrative.
C. **Anthropic direct for the core; OpenRouter for the Week-3 eval** — ~$5 top-up keeps the native path; use OpenRouter later where model-swapping is the actual requirement.

### Decision
Option C.
- Generation core stays on the native Anthropic SDK (`anthropic.Anthropic`), pinned to `https://api.anthropic.com` and using certifi's CA bundle so it ignores the corporate proxy env and verifies TLS regardless of shell state (see `src/generation/generator.py`).
- OpenRouter is reserved for Week 3's Claude-vs-GPT-4o faithfulness eval, where a single OpenAI-compatible endpoint with a swappable model string is genuinely the right tool.

### Rationale
1. **The API surface differs even though the model weights don't.** OpenRouter exposes an OpenAI-compatible API. Claude *via* OpenRouter is the same model, but the request shape is not — native Anthropic **prompt caching (`cache_control`)** and **structured-citation tool use** do not translate cleanly through the OpenAI-compatible layer. Both are load-bearing interview signals (the "80% cache-hit / ~55% cost-routing" story and "schema-validated citations beat regex").
2. **Cost is not the real axis.** Week 1 generation testing is cents; ~$5 direct covers it. Routing through OpenRouter to avoid a $5 top-up trades away two interview signals for no meaningful saving.
3. **OpenRouter still has a real home** — its provider-swapping is exactly what the multi-model eval wants. Right tool, later phase.
4. **Work/personal boundary.** The corporate gateway is a Salesforce asset; a personal portfolio project should hit Anthropic directly with a personal key. Pinning `base_url` in code enforces that boundary permanently, not per-shell.

### Interview framing
> "Same model weights, different API. I kept the generation path on Anthropic's native API specifically to use prompt caching and structured tool-use for citations — those are the mechanisms behind my cost and groundedness numbers. I did wire in an OpenRouter path, but only for the multi-model eval, where swapping Claude for GPT-4o with one string is the whole point."

### Trade-offs
- **Gain:** preserves native caching + tool-use (interview signals); clean work/personal separation; OpenRouter used where it's actually superior.
- **Lose:** a tiny out-of-pocket top-up; two code paths (native for core, OpenAI-compatible for eval) instead of one.

### Revisit trigger
If Anthropic access is ever unavailable for a live demo, the documented fallback is OpenRouter for generation (accepting the loss of native caching/tool-use) — a graceful-degradation story, not the default.

> **Triggered 2026-10-04 → DEC-018.** It turned out to be cheaper than expected: OpenRouter's *Anthropic-compatible* endpoint keeps the native SDK, tool use and `cache_control`, so nothing was lost.

---

## DEC-016: Week-4 production layer + what was deliberately scoped out
**Date:** 2026-07-14 (Week 4)

### Built
- **Related-ticker recommendations on shared infra** (`related_tickers.py`): per-
  ticker centroids over the SAME voyage-finance-2 vectors that power retrieval →
  cosine-NN. No new model, no separate index — the recs ride the retrieval
  embedding space. This is v2.3 interview moment #5 ("retrieval and recommendation
  are the same problem"), made literal. Verified sensible (AAPL→GOOGL/ADSK/NOW;
  LLY→MRNA at 0.62).
- **Cost tracker** (`cost_tracker.py`): per-query $ from token usage; Haiku priced
  10× under Sonnet — the concrete cost-routing metric. Logs to cost_log.jsonl.
- **Failure-mode logger** (`failure_tracker.py`): 5-mode classifier. Notably,
  honest abstention ("INSUFFICIENT EVIDENCE") is explicitly NOT classified as
  hallucination — the trust design and the eval agree.
- **`/recommend` + `/feedback` endpoints**, cost+failure surfaced in `/query`,
  startup warmup migrated to the modern lifespan handler.
- **5-tab Streamlit** (Ask / Conflict / Related tickers / Observability / Business
  value) — the multi-scenario demo surface.

### Deliberately scoped OUT (with reasons — the discipline signal)
- **Multi-turn (last-3) context:** low ROI on a tab-based single-query UI; would
  rework streaming + session state for modest gain. Deferred, documented.
- **Claude-vs-GPT LLM bake-off (DEC-010 harness exists):** the spec's "GPT-4o"
  target is ~2 generations stale; a rigorous current comparison needs a bigger
  labeled set than 40 queries to be meaningful, and costs tokens. Scoped out as a
  judgment call, harness left in place.
- **MLflow experiment tracking:** the ablations are one-shot, not iterative —
  MLflow would be theater for 3 static runs. Used git-versioned JSON results
  instead. Would earn its place once experiments become iterative.

### Verifiable-now vs credit-gated
All Week-4 code is unit-tested with NO API calls (23 tests, CI-green). What needs
a funded pipeline to validate — live end-to-end, the locust P95 number, the demo —
is explicitly deferred, not faked. The locustfile is committed as the load-test
*definition* with a cost warning; running it is a budgeted action.

---

## DEC-015: Eval methodology — pooled-LLM relevance, and reading the numbers honestly
**Date:** 2026-07-13 (Week 3)

### Context
The "rigor" artifacts: a 50-query golden set + 3 ablations + RAGAS. Building them
surfaced several measurement realities that matter more than the headline numbers.

### Decisions & findings
1. **Relevance labels via LLM pooling.** No human gold labels, so for each query
   we pool the top-K chunks from all configs, LLM-judge each relevant/not, and
   score every config against those labels. Standard IR pooling (avoids biasing
   toward one retriever). Framed as LLM-labeled, not human-gold — honest about it.
2. **Retrieval ablation (the headline): hybrid+rerank beats dense by +27.4%
   NDCG@10** (n=40) — clears the ≥10% gate. The nuance is the real story: **hybrid
   alone captures most of the lift**; reranking sharpens *ordering* (MRR/NDCG) but
   slightly lowers *Recall* — it reorders the top set, doesn't retrieve more.
   Reading that trade-off correctly is a better interview signal than a clean
   monotonic table.
3. **RAGAS faithfulness 0.806 — passes the 0.80 North Star gate** (Claude judge +
   Voyage embeddings, not the OpenAI default). Two debugging notes: (a) citation
   `[N]` markers + markdown had to be stripped before scoring (RAGAS's claim
   extractor choked on them — measurement artifact worth ~+0.06); (b) the judge
   needed max_tokens=4096 or it threw LLMDidNotFinish and corrupted scores
   (~+0.15 once fixed). **answer_relevancy stayed low (~0.20)** — and that's a
   *real* tension, not a bug: our answers deliberately hedge when evidence is thin
   ("the chunks confirm X but not Y"), which RAGAS penalizes as "incomplete." Our
   groundedness-first design intentionally trades relevancy-completeness for
   honesty. Documented as the intended trade-off.
4. **Chunking ablation: near-flat on a 60-doc subset** (paragraph marginally best
   on Recall, 0.25 vs 0.20; differences within noise). Reported as-is with the
   caveat that the golden queries target the full corpus, so a subset under-
   retrieves regardless of strategy — a conclusive result needs a full-corpus
   re-index (deferred). NOT cherry-picked into a clean "paragraph wins" table.

### Rationale
Every one of these is a place I could have quietly shown a better number (pad the
prompt for cache hits, drop answer_relevancy, hand-pick chunking labels). The
decision was consistently to **report the honest number + the reason** — because
in an interview, "faithfulness passes at 0.806, and here's exactly why
answer_relevancy is low and why that's the design working" is stronger than a
suspiciously-clean scoreboard.

### Revisit trigger
Full-corpus chunking ablation; Claude-vs-GPT-4o LLM comparison (DEC-010 OpenRouter
path); human-labeled relevance subset to validate the LLM-pooled labels.

---

## DEC-014: Query-relative temporal recency boost (not wall-clock "newest")
**Date:** 2026-07-12 (Week 2)

### Context
v2.3 specs a recency boost: "+0.15 for the last 2 quarters." That assumes a
*live* corpus where "recent" = "newest." FinSight's corpus is **historical**
(2019–2023) and the demo centers on the March 2020 window (DEC-005). A naive
"boost newest" would always favor 2023 chunks — actively *hurting* a query like
"What did Apple say about iPhone demand in Q1 2020?"

### Decision
Recency is **relative to the period the query is about**, not the wall clock.
- Node 1 (query understanding, Haiku) extracts a `temporal_reference` (year +
  optional quarter) from the query.
- The rerank node boosts chunks by proximity to that reference: full
  `recency_boost_weight` within `recency_boost_quarters`, linear decay to zero by
  2× that span. No temporal reference in the query → no boost (pure relevance).
- A `staleness_flag` fires when even the closest retained chunk is far (> 2× span
  quarters) from the reference — surfaced in the API response and driving honest
  abstention.

### Rationale
1. **Correct for a historical corpus.** "Q1 2020" now surfaces 2020 chunks;
   "2022" surfaces 2021–2022 chunks — verified. Same corpus, query-adaptive order.
2. **Staleness = honesty.** A query about 2015 (pre-corpus) flags stale and the
   generator abstains rather than answering from off-period chunks. Verified.
3. **Better interview story than the spec's literal version:** "I adapted recency
   to the shape of the data — on a historical corpus, boosting the newest chunk is
   wrong; I boost toward the period the query references, and flag staleness when
   the corpus can't cover it."

### Trade-offs
- **Gain:** period-accurate retrieval + honest staleness signal on a fixed corpus.
- **Lose:** depends on Haiku correctly extracting the period (degrades to no-boost
  pure relevance on failure — safe). A live corpus would also want a wall-clock
  component; easy to add when data becomes live.

### Revisit trigger
If the corpus becomes live/streaming, add a wall-clock recency term alongside the
query-relative one.

---

## DEC-013: Native server-side hybrid (BM25+dense RRF) + a linear LangGraph pipeline
**Date:** 2026-07-12 (Week 2)

### Context
Two Week-2 architecture choices: (1) how to do hybrid BM25+dense retrieval, and (2) how to orchestrate the query flow (query-understanding → router → retrieve → rerank → generate).

### Decision 1 — hybrid retrieval
Use Qdrant's **native server-side RRF fusion** in one query: two `Prefetch` legs (dense voyage-finance-2 + sparse BM25) fused by `FusionQuery(Fusion.RRF)`. BM25 sparse vectors generated with `fastembed` (`Qdrant/bm25`, a statistical model — onnxruntime ~73MB, fits the free tier). Sparse vectors added to all 15,023 points (local + cloud) via `scripts/add_sparse_vectors.py`. Dense-only mode retained (`retrieval_mode` config) for the Week-3 ablation.

**Rationale:** This is the DEC-002 "native hybrid in one query" story made real — no client-side fusion, no second round-trip, one call returns RRF-ranked results. It's the reason Qdrant was chosen over Pinecone (which needs separate sparse/dense indexes fused client-side).

### Decision 2 — LangGraph pipeline
Wrap the flow in a compiled `StateGraph` (`graph.py`) with a shared `FinSightState` TypedDict and five node functions (`nodes.py`). The router and query-understanding nodes use **Haiku** (cheap classification/rewrite); only generation uses **Sonnet** — the cost-routing story in concrete per-node latencies (Haiku ~700-900ms vs Sonnet generate ~5-8s). LangSmith tracing auto-enabled → per-node spans.

**Why linear (not conditional branching) for Week 2:** the router classifies into 3 paths, but `financial_metrics` and `risk_and_events` need the SEC corpus, which isn't ingested yet. So all paths currently retrieve from the transcript corpus, and non-earnings queries **correctly abstain** ("INSUFFICIENT EVIDENCE") rather than hallucinate. Conditional per-path retrieval branching lands when the SEC data is ingested. This is an honest, documented interim state — the routing decision is correct; the data just isn't there yet.

### Trade-offs
- **Gain:** genuine native hybrid; a real 6-node DAG (the #1 whiteboard interview artifact); cost-routing measured in numbers; graceful abstention on un-ingested paths.
- **Lose:** the LangGraph wrapper adds orchestration structure over what worked as plain functions — justified by the interview signal and the clean seam it gives for adding conflict-detection / guardrail nodes in Weeks 3-4.

### Revisit trigger
When SEC fundamentals + 10-K risk factors are ingested: add conditional edges so `financial_metrics` / `risk_and_events` retrieve from their own corpora, and the router's abstentions turn into real answers.

---

## DEC-012: voyage-finance-2 retrieval "looked worse" — it wasn't; cross-model scores aren't comparable
**Date:** 2026-06-23 (Week 2 — embedding backend swap)

### Context
Switched the embedding backend from bge-m3 (Week 1) to voyage-finance-2 to (a) fit Render's 512MB free tier — an API embedder needs no local model — and (b) get the domain-tuned finance model (DEC-003). After re-embedding all 15,023 chunks, top-k results looked *worse*: cosine scores dropped from ~0.60 (bge-m3) to ~0.40 (voyage), and top hits read as mid-sentence fragments.

### Investigation
Three direct checks:
1. **Model discrimination** — query vs a hand-written relevant doc = 0.51 cosine; vs irrelevant = 0.11. voyage cleanly separates on-topic from off-topic. ✓
2. **Storage integrity** — pulled a stored Qdrant vector, re-embedded its full DuckDB text, cosine = 1.0. Vectors correspond to the right chunks. ✓
3. **The "fragments"** — earnings-call transcript chunks *are* mid-sentence passages (continuous speech, ~2,900 chars). bge-m3 returned the same style; it just assigned higher absolute scores.

### Conclusion
No bug. **Cosine scores are not comparable across embedding models** — voyage-finance-2's distribution simply runs lower than bge-m3's. Judging one model's retrieval by another's score scale is apples-to-oranges. The alarming "0.60 → 0.40 regression" was a category error on my part.

### What this does NOT settle
Whether voyage is measurably *better* than bge-m3 on THIS corpus. Eyeballing can't answer that — it requires the golden-set ablation (Recall@K, MRR, NDCG), which is the Week 3 deliverable and the exact "hybrid+rerank beats dense by X% NDCG" interview artifact. Deploy proceeds on voyage; the quality delta gets proven rigorously in Week 3, not asserted.

### Trade-offs
- **Gain:** free-tier-deployable (no local model), domain model in place, and a documented reminder never to compare raw scores across models.
- **Lose:** nothing measured yet — the bge-m3-vs-voyage quality claim is deferred to eval, honestly.

### Revisit trigger
Week 3 ablation. If voyage does NOT beat bge-m3 on NDCG for our corpus, reconsider — but note bge-m3 can't deploy to free tier regardless, so a loss would mean "pay for a bigger host to keep bge-m3" vs "keep voyage." That's a cost decision, decided with numbers then.

---

## DEC-011: Inline [N] citations over forced tool-use — to preserve streaming
**Date:** 2026-06-23 (Week 1 Day 5 — generation latency)

### Context
v2.3 specced structured citations via Claude tool use with a Pydantic schema ("defensible; beats regex"). First implementation did exactly that: a required `emit_answer` tool with `tool_choice: {type: "tool"}`, whose schema forced per-claim citations. It worked and produced clean structured output — but measured **~11s to first token**. v2.3 also specs "first token < 500ms makes 3s P95 feel fast." Those two requirements collided.

### Root cause
With forced `tool_choice`, Claude buffers the *entire* tool-input JSON internally before emitting any stream event — so `answer_text` doesn't surface until generation is nearly done. Isolated test: plain-text streaming first token = **1.16s**; forced-tool-use first token = **11.6s**. The structure guarantee costs the streaming UX.

### Options considered
A. **Keep forced tool-use, drop streaming** — clean structure, but 11s dead air; fails the UX principle and demos badly.
B. **Two calls** — stream plain text, then a second call to structure citations. Doubles cost + latency.
C. **Inline [N] citations in streamed plain text, parsed post-hoc** — model writes "revenue grew 17% [3]" as it streams; regex-parse [N] markers into structured Citation objects mapped to source chunks.

### Decision
Option C. Stream plain text with inline [N] markers; parse them into structured citations from the completed text (`_parse_citations` in `generator.py`). Measured: **1.3s first token, ~8.5s total (warm)**.

*Note (2026-10-15):* this is a Week-1 measurement, taken before the query-understanding, router, rerank and conflict nodes existed (DEC-013, Week 2). Those nodes all run before the first token. End-to-end TTFT on the live deploy is **4.3s** (DEC-018). The two numbers measure different paths; they don't contradict each other.

*Note (2026-10-16):* re-measured on `/query/stream` across the four grounded eval questions: TTFT **3.6s median (n=4, range 3.4–3.9s)**. Pre-generation node medians (n=9, `/query`) are understand 1.2s, route 0.9s, retrieve 0.3s, rerank 0.15s, ~2.6s in total. Source: `evals/results/live_measurements_20261016T045744Z.json`.

### Rationale
1. **Both requirements met in one call** — sub-second first token AND structured, source-mapped citations. No second call, no cost penalty.
2. **This is how production RAG does it** (Perplexity, Bing Copilot all use inline citation markers over streamed text) — a more defensible interview answer than a purpose-built tool.
3. **The "beats regex" concern is narrower than it looked** — regex is fragile when parsing *free-form* model prose for citations, but parsing a constrained `[N]` marker the model was explicitly instructed to emit is robust. The structure lives in the prompt contract + a trivial, total regex, not in brittle pattern-matching of natural language.

### Trade-offs
- **Gain:** streaming UX (the load-bearing demo signal), single call, production-idiomatic.
- **Lose:** the citation structure is not *schema-enforced* by the API — a malformed answer with no [N] markers yields zero citations rather than an API-level error. Mitigated by the prompt contract and the fact that missing citations are visibly detectable (empty citation list in the UI).

### Revisit trigger
If groundedness eval (Week 3 RAGAS) shows citation coverage dropping, revisit: either tighten the prompt, or offer a non-streaming "strict mode" that uses forced tool-use for eval runs while streaming stays the default for the live demo.

---

## DEC-009: Rebalanced portfolio signal from eval-depth to deployment-judgment for the SA/FDE/PM role band
**Date:** 2026-05-31 (Week 1 — positioning review)

### Context
Target roles sharpened from "Principal SA / FDE / Applied AI" to a tighter band: **Forward-Deployed Engineer (and FDE lead/manager), Director, Principal Solutions Architect, TPM, and AI Product Manager** — across AI-native companies broadly. Every one of these is a *technical-credibility + customer/stakeholder-judgment* seat. None is a deep-research or pure-MLE seat.

v2.3's heaviest technical investment is the eval suite: 3 ablation tables + MLflow experiment lineage + a Claude-vs-GPT-4o multi-LLM comparison. That stack is calibrated to the **research/MLE signal** — the one band we have explicitly stepped out of. Meanwhile, nothing in v2.3 directly demonstrates the band we are now *in*: can this person handle a messy real-world deployment in front of a customer? The strongest raw material for that story already exists (the DEC-005 OHLCV sourcing battle) but it is buried as a footnote, not surfaced as an artifact.

### Options considered
A. **Rewrite the spec as v2.4** — re-scope eval work down, add deployment work in. Clean on paper, but re-opening a deliberately scope-locked spec creates version churn and undercuts the disciplined-scoping narrative that makes the project interview well.
B. **Hard-cut eval depth now** — immediately demote MLflow lineage + multi-LLM compare to "future work," reclaim the hours this week. Decisive, but destroys MLE-backup optionality before we know whether Week 3 even runs short.
C. **Record the decision, keep the spec intact** — keep the single headline retrieval ablation (the universal "decisions-with-numbers" artifact), log the *intent* to demote the deeper eval work, and make the actual cut at the Week 3 Sunday review based on real schedule pressure. Add the deployment-judgment artifacts (playbook + positioning doc) now, since they are pure additive leverage with no scope risk.

### Decision
Option C.
- **Keep** the one headline retrieval ablation: *hybrid+rerank beats dense-only by X% NDCG at $Y/query.* This is a universal talking point — SA, FDE, TPM, and PM interviewers all reward "I made this decision with a number."
- **Record intent** to demote MLflow lineage + the Claude-vs-GPT-4o comparison to one-line "future work" entries — but **only if Week 3 time slips.** The v2.3 Week 3 plan is left untouched; the call is deferred to the Week 3 cut.
- **Reinvest** any freed hours into `docs/deployment-playbook.md` — promoting the DEC-005 messy-data saga from footnote to a forward-deployed war story.
- **Add** `docs/interview-positioning.md` to map each target role to the artifact that answers its core question.

### Rationale
1. **Signal-to-role fit.** For an FDE/SA interviewer the load-bearing question is "would I send this person to a customer site?" A clean benchmark table doesn't answer it; a "here's how I'd deploy this at a regulated fund, and here's the dirty data I already wrestled" narrative does.
2. **The deployment story is already lived, not invented.** DEC-005 (yfinance broke after Yahoo's 2024 API change; Stooq captcha-gated; fell back to known-good data and shifted the demo to the March 2020 crash) is a genuine forward-deployed war story. Retroactive-sounding entries read as fake in interviews; this one is real.
3. **Preserve optionality cheaply.** Deferring the eval-cut to Week 3 costs nothing now and keeps the MLE-backup signal alive until we actually need the hours.
4. **No version churn.** Logging this as a decision rather than a v2.4 *is itself* the disciplined-scoping signal these roles screen for.

### Interview framing
> "I scoped the eval work to one headline ablation with a real number, and deliberately *didn't* go deeper on experiment-tracking lineage — because for the roles I'm targeting, the higher-value signal was deployment judgment, not benchmark depth. So I wrote up how I'd actually roll this out at a regulated customer, including the data-sourcing problems I hit and how I fell back to known-good data. I made that call explicitly and logged it — that's the kind of scope decision I'd make on a real engagement."

### Trade-offs
- **Gain:** the project now speaks directly to the customer-facing role band; deployment judgment becomes a first-class artifact instead of a footnote; no spec churn.
- **Lose:** thinner MLE/research-depth signal (experiment lineage, multi-model eval rigor). Acceptable while AI-PM/SA/FDE is the primary target; recoverable via the revisit trigger.

### Revisit trigger
At the Week 3 Sunday cut — decide then whether MLflow lineage + multi-LLM compare actually get demoted, based on real schedule pressure. Separately: if the search pivots back to MLE-primary, the demoted eval depth is the first thing to restore.

---

## DEC-017: Built the deferred two-tower fine-tune + re-expressed observability in W&B Weave

### Decision
Promoted the Phase-6 "stretch" two-tower bi-encoder fine-tune (spec v2.3 "next direction") from deferred to **built**, and added a second observability path in **W&B Weave** alongside the existing LangSmith spans. Motivation: the target role band now includes CoreWeave-style training/GPU-infra roles, and CoreWeave owns Weights & Biases — so a real PyTorch fine-tune with a Weave trace tree is directly on-signal.

### What was built
- **Fine-tune** (`scripts/finetune_biencoder.py`): contrastive bi-encoder training with `MultipleNegativesRankingLoss` (in-batch negatives) over (query → positive chunk) pairs, honest before/after Recall@5 / MRR@10, CUDA/MPS/CPU device selection, model saved to `artifacts/`.
- **Training data** (`scripts/build_finetune_pairs.py`): provider-agnostic (OpenAI/OpenRouter/Gemini) generator of analyst-question→chunk pairs, **leakage-guarded** — excludes every chunk used as a golden-set seed, so training pairs and the 40-query held-out eval never share a source chunk.
- **Weave tracing** (`src/observability/weave_setup.py` + `@op` on all 6 graph nodes): the same retrieve→rerank→generate spans as LangSmith, re-expressed in Weave; off unless `WEAVE_ENABLED`.

### Result (honest)
Trained bge-small on **48** Gemini-generated in-domain pairs, evaluated on **40 held-out golden queries** against a **3000-chunk** pool: **Recall@5 0.825 → 0.870 (+4.5 pts mean, range +2.5 to +5.0)**, **MRR@10 +1.4 pts mean (range +0.9 to +2.6)**, across **5 training seeds, positive on all 5**. Modest training set → modest-but-consistent lift. Per-seed results in `evals/results/finetune_seeds/`, each run logged to W&B (`ameyparmarthi-finsight/finsight-biencoder-finetune`).

**Second debugging beat — seed variance:** an early re-run of the identical config gave +2.5 instead of +5.0. Cause: the training shuffle was unseeded. At n=40, one query = 2.5 pts, so a single run's lift is within noise. Fix: seed torch (verified — same seed reproduces exactly), run 5 seeds, report mean + range instead of one number.

**The debugging story:** the first run used a 300-chunk eval pool and showed the base model already at **Recall@5 = 1.000** — a ceiling that made any "lift" meaningless. Diagnosed it as an eval that was too easy (small pool + generation-bias) *and* a training set of only 32 self-split pairs. Fixed both: a realistic 3000-chunk pool and a leakage-free expanded training set evaluated on the full golden set.

### Almost chose
Framing the marginal first result (+0.0 Recall) as "fine-tuning didn't help — here's why" (a mature but weak demo). Rejected: the honest problem was eval design and training-set size, both fixable, so fixing them beat rationalizing a null result.

### Interview framing
> "I fine-tuned a bi-encoder retriever with an in-batch-negative contrastive loss on domain pairs, then measured it honestly on a held-out set against a realistic corpus pool — Recall@5 up 4.5 points on average across 5 seeds, positive on every seed. I report mean and range because at 40 eval queries one query is 2.5 points — a single run would be noise. The interesting part was the *first* run: base model was at Recall ceiling because my eval pool was too small, which taught me the eval was the bug, not the model. Small training set (48 pairs), so the lift is modest but real and measured, not asserted. Next step is scaling the pairs and running it on an actual GPU."

### Trade-offs
- **Gain:** a genuine PyTorch training + Weave-observability artifact for the CoreWeave/MLE band; an honest eval-design war story.
- **Lose:** small training set (Gemini free-tier rate limits capped generation at 48 pairs); ran on Apple MPS, not a real GPU — so no throughput/profiling story yet.

### Revisit trigger
Before leaning on this as a headline: scale to 500+ training pairs and re-run on a real GPU (CoreWeave/Colab) to add a training-throughput + Recall-curve story. W&B runs are synced online and demoable.

---

## DEC-018: Claude via OpenRouter's Anthropic-compatible endpoint — gateway as a config switch
**Date:** 2026-10-04 (making the live demo self-sustaining)
**Supersedes:** DEC-010's rationale #1 (for the generation core).

### Context
The live Render demo returned a 500 on `/query`: the personal Anthropic key was back at $0 credit. Remaining credit: OpenRouter ($10), GCP/Vertex Gemini. The demo had to work again without a new top-up, and a provider outage should never surface as an opaque 500.

### Options considered
A. **Gemini (Vertex) for the core** — largest runway. But it means rewriting 4 call sites (forced tool use, streaming, citation parsing), and every measured number (RAGAS 0.806, the ablations) was produced with Claude. Swapping the generator invalidates the evals the demo is built on.
B. **OpenRouter via its OpenAI-compatible API** — the path DEC-010 rejected: different request shape, so `cache_control` and Anthropic tool use don't translate cleanly.
C. **OpenRouter via its Anthropic-compatible Messages endpoint** (`https://openrouter.ai/api`) — the same `anthropic` SDK, with only `base_url`, key and model ids changing.

### Decision
Option C, as a config switch rather than a second code path.
- `src/utils/llm_client.py`: one shared `anthropic_client()` for all serving call sites (generator, query-understanding/router nodes, conflict detector). `LLM_GATEWAY=anthropic|openrouter` picks the pinned base URL and key. The corporate-proxy guard from DEC-010 still holds, because `base_url` is never taken from the environment.
- Model ids are env-configured (`anthropic/claude-sonnet-4.6`, `anthropic/claude-haiku-4.5` on OpenRouter). The cost tracker maps them to the same price table, since OpenRouter passes through Anthropic list prices.
- **Graceful degradation:**
  - Any `anthropic.APIError` on `/query` now returns a **503** that says retrieval is healthy and to retry.
  - `/query/stream` emits an SSE `event: error`, which the Streamlit UI renders as a warning instead of hanging.
  - A missing key (`LLMConfigError`) also returns a 503, and `/health` reports `llm_gateway` + `llm_key_configured`. The first Render deploy hit exactly this: the gateway var landed but the key didn't, and `/query` 500'd.
  - Tests cover all three cases.
- **Explicit timeouts on every upstream client.** Demo rehearsal hit requests that never returned. The SDK defaults were the cause: Voyage `timeout=None` (hang forever), Cohere 300s, Claude 600s. Now Voyage is 30s with 2 retries, Cohere is 15s (it falls back to retrieval order), and Claude is 60s (the slowest real call is ~25s). A stuck dependency now becomes a fast 503 or a degraded answer instead of a hung request.
- **Spend cap moved to the gateway.** `max_cost_per_query_usd` and `daily_api_budget_usd` were defined in config but enforced nowhere, so they're deleted. An in-process daily counter would reset on every Render free-tier spin-down. The hard cap is a spend limit on the OpenRouter key, where the state persists.

### Verified (live, before committing)
- Haiku forced tool use returned a schema-valid route.
- Sonnet streaming put the first token out at 0.9s.
- The full pipeline on Qdrant Cloud ran 5/5 golden queries grounded, with citations.

### What the measurement exposed
Cost is **$0.0135/query mean (n=5, range $0.012–0.015)**, not the ~$0.005 the README claimed.
- The floor is ~3.2K input tokens of retrieved evidence to Sonnet. That alone is ~$0.0096.
- The tracked figure covers Sonnet plus retrieval. The two Haiku nodes add about $0.002 that the tracker doesn't count yet, so true cost is about $0.015.
- `cache_read_tokens` was 0 on every call. The static system prompt is ~300 tokens, below Sonnet's 1,024-token cache minimum, so `cache_control` is wired but never fires. The evidence block changes per query and can't be cached.
- **Latency was also over target.** On the live deploy, first streamed token arrives at 4.3s and the full answer at ~12–15s, against a P95 ≤ 3s target. Conflict-check queries take ~25–30s. These are single-user numbers; no load test has been run.
  - *Re-measured 2026-10-16* (`evals/results/live_measurements_20261016T045744Z.json`): first token **3.6s median** (n=4, 3.4–3.9s), full streamed answer **11.0s median** (10.7–11.7s), conflict-check queries **33.9–36.1s** end to end (n=3), and cost **$0.0139/query mean** (n=9, range $0.0103–0.0156; abstentions are the cheap end). Still single-user.
- Docs are now corrected to the measured numbers.
- Real levers, if cost mattered at scale:
  - Top-5 → top-3 chunks, about -35% input.
  - Haiku generation for simple metric lookups.
  - Tighter chunking.

### Interview framing
> "My Anthropic credit ran out with the demo live, and `/query` started 500ing. I didn't port to Gemini, because that would have invalidated every eval number I'd measured with Claude. I moved the gateway to OpenRouter's Anthropic-compatible endpoint: same SDK, same tool use and streaming, one env var. I also made provider failures degrade to a 503 that says retrieval is fine. Re-measuring live showed my cost claim was off by ~3×: $0.0135, not $0.005. Prompt caching wasn't firing because the prompt was below the cache minimum. I corrected the docs rather than keep a number I couldn't reproduce."

### Trade-offs
- **Gain:**
  - The demo runs on existing credit. $10 covers about 650 queries.
  - Provider choice is a deploy-time flag.
  - Outages degrade honestly.
  - The cost numbers are now measured rather than assumed.
- **Lose:**
  - A third party sits in the request path, adding a little latency and another dependency.
  - OpenRouter sees the prompts. That's acceptable for public filings, not for a regulated customer.
  - The eval modules (`ablation`, `faithfulness`, `golden_set`) still build their own direct-Anthropic clients. They're offline tools, so they're left out of this change.

### Revisit trigger
- Direct Anthropic credit restored → flip `LLM_GATEWAY=anthropic` (bare model ids). No code change.
- A regulated-customer deployment → direct or VPC-hosted provider only. No third-party gateway.
- Repeated OpenRouter errors → add Gemini as a *secondary failover* behind the 503 path, never as the primary. That keeps the eval numbers valid.

---

## DEC-019: Moved the live demo from Render free tier to Cloud Run, always on

**Date:** 2026-10-05 · **Status:** Accepted

### Context
The demo is opened by hiring managers clicking a README link, usually cold. On the Render free tier each service sleeps after 15 min idle. Measured cold start was **~51s for the UI**, then the API cold-starts behind it. The first impression was a spinner. Render also gave no log access from the CLI, so a mid-rehearsal instance restart (possibly OOM at 512MB) couldn't be diagnosed.

### Options considered
A. **Stay on Render, upgrade to paid** ($7/service/month). Fixes sleep, but adds no GCP signal and still has no logs.
B. **Keep Render free + a keep-alive pinger.** Free, but it fights the platform's ToS intent and still runs on ~0.1 vCPU.
C. **Cloud Run, `min-instances=1` on both services**, funded by the Google One AI Pro GCP credit.

### Decision
Option C. Render stays up as a backup URL until the Loom is recorded.
- **One image, two services.** The API image is built by Cloud Build and pushed to Artifact Registry (tag = git SHA). `finsight-ui` reuses it with the command overridden to Streamlit, so the UI and API can't drift.
- **Secrets in Secret Manager**, mounted as env vars. They're readable only by a dedicated `finsight-run` service account, not the default compute SA (which now holds build permissions).
- **Sizing:** API at 1 vCPU/1GiB (Render's 512MB was the suspected restart cause), UI at 1 vCPU/512MiB with session affinity (Streamlit holds a websocket per session). `max-instances=2` caps the blast radius of a traffic spike on LLM spend.
- `.gcloudignore`/`.dockerignore` cut the build upload from 244MB to ~600KB (excludes `qdrant_storage/`, the 128MB fine-tuned bi-encoder, data, evals).

### Verified (live)
- `/health` 0.57s: Qdrant reachable, 15,023 points, `llm_key_configured=true`.
- `/recommend/AAPL` 0.25s (shipped centroids).
- The 4 demo-script queries match Render behavior: COVID grounded (16s), guidance grounded with 0 conflicts (38s), Oracle grounded (12s), Apple 2015 refuses (5.6s). Cost $0.011–0.016/query.
- `/query/stream` emits tokens; the UI loads with "API healthy · 15,023 chunks".

### Trade-offs
- **Gain:** no cold start; real logs (`gcloud run services logs read`); 2× the memory; a GCP deploy story for the SA/FDE/CoreWeave conversations.
- **Lose:** it's no longer free. Two always-on instances are an estimated ~$20–25/month at idle rates, so the $50 credit covers roughly two months of interview season. LLM spend is still capped separately on the OpenRouter key.
- Latency is unchanged. The bottleneck is LLM generation, not hosting (DEC-018).

### Interview framing
> "The free tier was fine for building and wrong for the audience. A hiring manager clicking a link got a 50-second spinner. I paid for availability where it mattered: two always-on Cloud Run services from one image, secrets in Secret Manager under a least-privilege service account, and instance caps so a traffic spike can't run up the LLM bill."

### Revisit trigger
- Interview season ends → `--min-instances 0` (one command; cold start returns, cost goes to ~$0).
- Credit runs low → drop the UI to min 0 first; the API is the expensive cold start.
- Real traffic → load test before raising `max-instances`.

---

## DEC-020: Citation index invariant — [N] is chunks[N-1], never re-sorted client-side

**Date:** 2026-10-15 · **Status:** Accepted

### Context
The generator numbers evidence by position in the reranked chunk list it was given. The answer says "revenue grew 17% [3]", and `_parse_citations` resolves `[3]` to `chunks[2]` (DEC-011). The API returns `chunks` in that same order.

The new React frontend shows evidence cards beside the answer. Re-ordering those cards in the browser, by date, ticker or score, is a tempting UX change. It would silently point every `[N]` at the wrong passage. In a product whose whole claim is "every number is traceable", a wrong link is worse than no link.

### Options considered
A. **Sort client-side and renumber the answer text to match.** Rewriting model output in the browser is fragile, and the displayed answer would no longer match what the API returned or what was logged.
B. **Map by `chunk_id` instead of position.** It survives any re-ordering. But `CitationOut` exposes only `chunk_number` and `source_label`: the internal `Citation` has `chunk_id`, the API drops it. Grouped markers like `[1, 2]` also never reach the structured list. B needs an API contract change.
C. **Positional invariant:** `[N]` ↔ `chunks[N-1]`, and the chunk list is rendered in API order, never re-sorted.

### Decision
Option C, enforced in `frontend/src/lib/evidence.ts`.
- Inline markers are parsed from the answer text. Grouped forms (`[1, 3]`, `[4;2]`) expand to one anchor per chunk.
- Each anchor scrolls to evidence card N, which is `chunks[N-1]`.
- Out-of-range markers aren't linked. The live eval suite fails them as a citation-integrity error (DEC-022).
- Unit tests pin the invariant ("maps [N] to chunks[N-1] without re-sorting", "ignores out-of-range citations").

### Trade-offs
- **Gain:** no backend change. The link is correct by construction, and one test guards it.
- **Lose:** evidence can only be shown in rerank order. Any "sort by date" view would have to be a separate list that doesn't drive citation links.
- **Lose:** the frontend parses citations itself instead of trusting the structured `citations` array, because that array misses grouped markers. The two can disagree on which chunks were cited.

### Interview framing
> "The citation number is a pointer into an ordered list. The moment the UI re-sorts that list, every pointer is wrong and still looks right. I made the order an invariant with a test on it, instead of a convention someone breaks while polishing the UI."

### Revisit trigger
- The API adds `chunk_id` to `CitationOut` (or emits grouped citations) → switch to ID-based mapping. Re-sorting becomes safe.
- The backend ever paginates, dedupes or re-orders `chunks` after generation → this invariant breaks server-side first. Fix it there.

---

## DEC-021: Demo-mode fallback when the API is unreachable — stale data, clearly labeled

**Date:** 2026-10-15 · **Status:** Accepted

### Context
The frontend is a static site that calls the live API. If the API is down, the link a hiring manager clicks shows an error page. The backend can be down for reasons outside the frontend's control: Qdrant unreachable, a Cloud Run revision failing, LLM credit exhausted (DEC-018). DEC-019 removed cold starts, not outages.

### Options considered
A. **Show an error and a retry button.** Honest, but the visitor sees nothing of the product.
B. **Silently serve canned answers.** It always "works", but it misrepresents a stored response as a live system. That's the exact failure this project exists to avoid.
C. **Fall back to stored responses, labeled as such, with a path back to live.**

### Decision
Option C.
- **When it triggers:** on load the app calls `GET /health` with a 6 s timeout. A failure, a timeout, or a missing `points_indexed` (Qdrant unreachable) puts the app in demo mode. A live `/health` with `llm_key_configured=false` stays live, and queries then surface the API's 503.
- **What it serves:** responses from `frontend/src/lib/demo.ts`, a grounded answer, a refusal and related tickers, through the same rendering path as live results.
- **How it's labeled:**
  - A persistent "Demo mode" badge in the header.
  - The status tooltip says it's replaying a captured response and offers a click to retry.
  - The Evaluation page states that demo runs replay stored responses at no API cost.
  - Telemetry tags these events `mode='demo'`, and the dashboard excludes them.

### Trade-offs
- **Gain:** the UI, citations, trace and eval flow stay inspectable during a backend outage.
- **Lose:** the stored data is stale by definition. It won't reflect later corpus, prompt or model changes, so it can drift from what the live system would say.
- **Lose:** it's a second copy of response shapes to keep in sync with `QueryResult`.
- **Lose:** a flaky `/health` (slow but up) demotes a working backend to demo mode until the visitor retries.

### Interview framing
> "When the backend is down, the frontend degrades the same way the backend does: honestly. It shows a stored response with a badge that says so and a one-click retry. It never presents a recording as the live system."

### Revisit trigger
- The demo payloads drift visibly from live responses → regenerate them from real `/query` calls, and record the capture date in `demo.ts`.
- `/health` timeouts cause false demo mode → add a background re-check instead of a one-shot probe.

---

## DEC-022: Live behavioral eval in the UI — 9 cases + citation integrity via non-streaming /query

**Date:** 2026-10-15 · **Status:** Accepted

### Context
The offline benchmark (RAGAS faithfulness 0.806, n=40; +27.4% NDCG@10) is a point-in-time measurement of retrieval and generation quality (DEC-015). It runs from the CLI, needs keys, and costs tokens, so it isn't in CI. It doesn't tell you whether the *deployed* system still behaves today:
- Does it still refuse advice questions?
- Does the conflict node still fire?
- Do `[N]` markers still resolve to real chunks after a prompt or model change?

### Options considered
A. **Re-run RAGAS more often.** It measures the wrong thing for this purpose, and it's the expensive path.
B. **Add the behavioral checks to backend CI.** CI makes no API calls by design (dummy keys), so this would need live keys in CI and spend on every push.
C. **A small behavioral suite in the frontend's Evaluation page,** run on demand against whatever API the UI points at.

### Decision
Option C, in `frontend/src/lib/eval-suite.ts`.
- **Cases:** 9, drawn from the Ask page's example questions (4 grounded, 2 conflict-check, 3 refusals). A unit test asserts every example question is covered.
- **Checks per case:**
  - Expected behavior. Grounded cases must answer and refusal cases must abstain. Conflict cases require `detect_conflicts` to have actually run (non-zero node latency), not merely zero conflicts found.
  - Citation integrity. Every inline `[N]` and structured citation must fall in 1..`chunks.length`.
- **Endpoint:** the suite uses non-streaming `POST /query`, not `/query/stream`. The stream's `done` event carries no `cost_usd` or `failure_mode`, so only `/query` gives exact per-run cost.
- **Summary:** pass rate, abstention accuracy, p50/p95 latency, total cost and tokens. Errored cases are excluded from latency.

### Trade-offs
- **Gain:** a regression check anyone can run from the browser in one click, with exact cost. It catches the failures that matter for trust: broken citations, a guardrail that stopped refusing, a conflict gate that silently turned off.
- **Lose:** 9 cases is a smoke test, not a benchmark. It says nothing about faithfulness or retrieval quality. Those stay with RAGAS and the ablations. **This complements the offline evals; it doesn't replace them.**
- **Lose:** pass/fail is heuristic (abstention is detected from the `INSUFFICIENT EVIDENCE` sentinel or `grounded=false`). Each run spends real API cost, and results aren't persisted to `evals/results/`.

### Interview framing
> "Offline evals told me the system was good once. The live suite tells me it's still behaving: it refuses what it should, cites only chunks that exist, and actually runs the conflict check. It's nine cases on purpose. It's a smoke alarm, not a benchmark."

### Revisit trigger
- Before relying on it for release decisions → persist each run (timestamped) for regression tracking, and grow the case set from the golden set.
- The stream `done` event gains `cost_usd` → the suite could use the streaming path and measure TTFT too.

---

## DEC-023: Client telemetry in Bolt Database (Supabase Postgres) instead of a vendor SDK

**Date:** 2026-10-15 · **Status:** Superseded by DEC-024 (2026-10-16)

> **Superseded:** the browser no longer writes to Supabase. Telemetry now goes through FastAPI into Neon Postgres, with rate limiting (DEC-024). The privacy rule and the table shapes carried over unchanged. Kept for the record.

### Context
LangSmith and the backend JSONL logs see the pipeline, not the user. What a visitor actually experienced in the browser went unrecorded: time to first token, aborted queries, client-side crashes. The frontend was built on Bolt, which provides a Supabase Postgres database ("Bolt Database"), so a store already existed with no new vendor.

### Options considered
A. **A vendor RUM/analytics SDK** (Sentry, PostHog, Datadog RUM). Session replay, alerting and dashboards out of the box. It's another third-party script and account, and some of these capture more than needed, including inputs.
B. **Log from the backend only.** It can't see TTFT as the browser renders it, client errors or cancellations.
C. **Two insert-only Postgres tables plus one aggregate function** in the existing Bolt Database.

### Decision
Option C. The schema is in `frontend/supabase/migrations/`; the client is `frontend/src/lib/telemetry.ts`.
- **`query_events`:** one row per query. Outcome (grounded / abstained / error / cancelled), mode (live / demo), routing path, TTFT, total latency, chunk count, tokens, and cost (non-streaming runs only).
- **`client_errors`:** uncaught errors from the React error boundary, `window.onerror` and unhandled rejections.
- **Privacy:** question text is never stored. Session IDs are random per tab.
- **Security:**
  - RLS allows `INSERT` only for `anon`/`authenticated`, and only if `created_at` is within the last minute. There's no `SELECT` policy.
  - CHECK constraints bound every column: lengths, enums, and numeric ranges such as latency ≤ 600000 ms.
- **Reads:** only through `telemetry_summary(window_hours)`.
  - It's a `SECURITY DEFINER` function that returns aggregates over live-mode rows.
  - The window is clamped to 1–720 hours, and `EXECUTE` is revoked from `PUBLIC` and granted to `anon`/`authenticated`.
- **Optional:** telemetry is off unless `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set at build time.

### Trade-offs
- **Gain:** no new vendor, and no PII or question text leaves the browser. The browser can write but never read raw rows. The whole design fits in one reviewable SQL file.
- **Lose:**
  - No session replay, no alerting, no automatic error grouping or source maps. Someone has to look at the dashboard.
  - **The anon insert path is spammable.** The anon key ships in the bundle, so anyone can insert rows. CHECK bounds and the one-minute timestamp window limit the size and shape of junk; they don't limit the volume. Rate limiting (an edge function or per-session caps) is future work.
  - Telemetry depends on the Bolt-hosted project staying up. Inserts are fire-and-forget: a failed write logs a console warning and is dropped, so the app is unaffected but the data is lost.

### Interview framing
> "I needed to know what users actually experienced, not just what the pipeline did. Instead of dropping in a vendor SDK, I used two insert-only tables, with CHECK constraints on every column and a single SECURITY DEFINER function for reads. The browser can write but never read raw rows, and question text is never stored. The open hole is volume: the anon path is spammable. I said so, and rate limiting is the next step."

### Revisit trigger
- Junk or abusive inserts show up → add rate limiting in front of the insert path (edge function or per-session caps).
- Real users and an on-call need → move errors to a vendor with alerting and source maps, and keep the privacy rule (no question text).

---

## DEC-024: Telemetry and feedback through FastAPI into Neon Postgres (supersedes DEC-023)

**Date:** 2026-10-16 · **Status:** Accepted

### Context
DEC-023 had the browser insert telemetry straight into Bolt's Supabase project using a public anon key. That left three problems:
- **Unbounded volume.** Anyone with the bundle could insert rows. DEC-023 named this as its open hole.
- **Off-stack.** The target stack is FastAPI + Pydantic + PostgreSQL, with no vendor BaaS for app data. Supabase was there only because the frontend was scaffolded on Bolt.
- **Lost feedback.** `/feedback` appended to `logs/feedback.jsonl` on the Cloud Run container's local disk. That is lost whenever an instance is replaced, including on every deploy.

### Options considered
A. **Keep Supabase and add an edge-function rate limiter.** This is the smallest change, but it keeps a BaaS on the data path and a database credential in the bundle.
B. **Cloud SQL for PostgreSQL.** It sits in the same GCP project with IAM auth, but it means a standing instance for a demo with near-zero traffic.
C. **Neon serverless Postgres behind FastAPI.** Compute scales to zero when idle. It's standard Postgres, so moving to Cloud SQL or RDS later is a connection-string change.

### Decision
Option C.
- **Data path:** browser → `POST /telemetry/query`, `POST /telemetry/error` → FastAPI → Postgres. The dashboard reads `GET /telemetry/summary?window_hours=` (1–720), which returns aggregates only. Raw rows have no read endpoint.
- **Schema:** `src/telemetry/schema.sql`, applied with `python -m scripts.init_db` (idempotent).
  - `query_events` and `client_errors` keep DEC-023's columns and CHECK constraints.
  - A new `feedback` table stores `/feedback`. Its request and response are unchanged.
  - Row-level security is gone: only the API connects.
- **Validation:** the Pydantic models mirror every CHECK bound, so bad input is a 422 before it reaches the database.
- **Rate limit:** 30 writes per minute per client IP on the three write endpoints, then 429.
  - It keys on the last `X-Forwarded-For` entry, which Cloud Run appends; earlier entries are client-supplied.
  - The counter is in-memory, per instance.
- **Connection:** the Neon *pooled* URL is stored in Secret Manager as `finsight-database-url` and exposed to Cloud Run as `DATABASE_URL`.
  - Each request opens one short-lived psycopg connection. Neon's PgBouncer does the pooling, and none of this is on the answer path.
  - `prepare_threshold=None`, because PgBouncer's transaction mode can't hold prepared statements.
- **Degradation:** with `DATABASE_URL` unset, `/telemetry/*` returns 503 and `/feedback` falls back to JSONL (local dev, CI). A database error is a 503. The query path never touches the database.
- **Neon setup:**
  - Region: AWS us-east-2, the closest offered region to Cloud Run us-central1.
  - Postgres only. Neon Auth, Functions, Realtime, the AI gateway and object storage are off.
  - The Supabase SDK and `frontend/supabase/` are removed.

### Trade-offs
- **Gain:**
  - The browser holds no database credential.
  - Volume is bounded per IP.
  - Feedback survives deploys.
  - One backend owns all writes, in the standard stack.
- **Lose:**
  - **Telemetry depends on the API.** When the API is down the frontend is in demo mode, and those events are dropped. Demo traffic was excluded from the summary anyway.
  - **The rate limit is approximate.** It's per instance (max-instances=2) and resets on deploy. Many IPs can still write junk, but only within the CHECK bounds.
  - **Latency on writes.** Each write pays a fresh TLS connection and a GCP Iowa → AWS Ohio hop. After an idle period, Neon's compute has to wake up first. Not measured; fire-and-forget hides it.
  - **Feedback persists question text** (first 300 chars, as before) with no retention limit. Telemetry still stores no question text.

### Interview framing
> "My first telemetry design had the browser write straight to a hosted Postgres with a public key, and I'd flagged volume as the hole. I moved it behind the API. Pydantic bounds mirror the CHECK constraints, there's a per-IP rate limit, and Neon Postgres scales to zero. The browser no longer holds a credential. The fix also caught a quieter bug: feedback was being written to a container's local disk and lost on every deploy."

### Revisit trigger
- Abuse shows up → move the limiter to Redis or Cloud Armor so it's shared across instances.
- Sustained traffic → add a psycopg connection pool, or batch writes.
- Feedback grows or real users arrive → set a retention policy for feedback text.

---

## DEC-025: React frontend on Vercel, calling the Cloud Run API directly

**Date:** 2026-10-16 · **Status:** Accepted

### Context
The React frontend (DEC-020…024) only ran locally. The live demo link pointed at the Streamlit UI on Cloud Run, which can't show the evidence panel, the pipeline trace or the live eval suite. The frontend is a static Vite bundle with no server code, so all it needs is a host and an origin the API allows.

### Options considered
A. **A third always-on Cloud Run service serving the bundle.** Everything stays in one GCP project, but it adds a standing container (DEC-019 already runs two) just to serve static files.
B. **Cloud Storage + Cloud CDN.** No container, but HTTPS on a custom domain needs a global load balancer, and there are no per-PR previews.
C. **Vercel, building from `frontend/`.** No idle compute, managed TLS on a custom domain, production deploys from `main`, and a preview URL on every PR.
D. **Vercel with a same-origin rewrite (`/api/*` → Cloud Run).** This removes CORS, but every request then comes from Vercel's edge. DEC-024's per-IP rate limit would only see Vercel's IPs, unless it trusted a forwarded header the client can spoof. It would also put a proxy hop in the middle of a ~35 s conflict-query stream.

### Decision
Option C.
- **Hosting:** Vercel project with Root Directory `frontend`, live at `https://finsight.ameyparmarthi.com` (a `finsight` CNAME → `cname.vercel-dns.com`).
- **API path:** the browser calls the Cloud Run API directly, including the SSE stream. `VITE_API_URL` is optional; blank falls back to the Cloud Run URL in `api.ts`.
- **CORS:** `CORS_ALLOW_ORIGINS=https://finsight.ameyparmarthi.com,http://localhost:5173` on Cloud Run. Verified: preflights from both origins return 200 with the matching `Access-Control-Allow-Origin`, and any other origin gets 400.
- **README:** the React UI is now the primary live-demo link. Streamlit stays as the secondary demo, and Render as the backup.
- **Verified end to end (2026-10-16):** the live site loaded in live mode, streamed a grounded answer, and recorded its `query_events` row through `/telemetry/query` (200). The verification row was then deleted.

### Trade-offs
- **Gain:**
  - The full evidence UI is the public demo, with nothing to keep warm on the frontend side.
  - Previews on every PR.
  - The API keeps seeing real client IPs, so DEC-024's rate limit still works.
- **Lose:**
  - **Previews run in demo mode.** `*.vercel.app` preview origins aren't on the CORS list, so a preview can't test against the live API. Testing against it means localhost or production.
  - **Two vendors on the request path** (Vercel + GCP), with two dashboards and two deploy pipelines.
  - **Networks that rewrite DNS can force demo mode.** Found during verification: a VPN whose DNS answered `*.run.app` with a `100.64.x.x` address made Chrome's Local Network Access check block the public page's calls to the API. The site fell back to demo mode, as DEC-021 designed. Off that VPN, the API resolves to public Google IPs and the site is live. Option D would avoid this, at the costs listed above.
- **Deploy gotcha found on the way:** `finsight-api` traffic had been pinned to a named revision, so the DEC-024 deploy created a healthy revision that served 0%, while gcloud reported the old one as "serving 100 percent". Fixed with `update-traffic --to-latest`; the check is in the README deploy section.

### Interview framing
> "The frontend is static, so I put it on Vercel and had the browser call the Cloud Run API directly. The same-origin proxy looked cleaner because it removes CORS, but it would have hidden every client IP behind Vercel's edge and broken my per-IP rate limit. So I kept the direct path and locked CORS to the production origin. Verifying it from my own laptop, the site dropped into demo mode. My VPN's DNS resolved the API to a private address, and Chrome blocked it. The fallback I'd designed for an API outage covered a network problem I hadn't planned for."

### Revisit trigger
- Previews need the live API → add the preview origin pattern to CORS, or give previews a separate API URL.
- Visitors behind DNS-rewriting networks report demo mode → revisit Option D, with a forwarded-header scheme the rate limit can trust.
- Interview season ends → nothing to scale down on the frontend side; see DEC-019 for the API.

---

## Format notes for future entries

- Write these **as they happen**, not retroactively. Retroactive entries sound fake in interviews.
- Always include the **option we almost chose but didn't**. That's the interesting part.
- Always include the **revisit trigger**. Shows you know decisions are not permanent.
- Numbers over adjectives. "8-10% NDCG lift" beats "significantly better."
