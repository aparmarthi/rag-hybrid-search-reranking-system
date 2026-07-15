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

## Format notes for future entries

- Write these **as they happen**, not retroactively. Retroactive entries sound fake in interviews.
- Always include the **option we almost chose but didn't**. That's the interesting part.
- Always include the **revisit trigger**. Shows you know decisions are not permanent.
- Numbers over adjectives. "8-10% NDCG lift" beats "significantly better."
