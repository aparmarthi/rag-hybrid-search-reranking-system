# Bolt.new prompt: FinSight UI (v2, verified against the live API)

Paste everything below the line into bolt.new.

> Verified on 2026-10-08 against the live API (revision `finsight-api-00002-jk5`, image `829b6b4`, CORS enabled). Every eval number comes from `evals/results/*.json` and the README.
>
> Changes from v1:
> - The real ablation values replace the TODO placeholders.
> - Evidence cards stay in server order, because `[N]` maps to `chunks[N-1]`. v1 said to sort by score, which would break the citation mapping.
> - The example questions are in-corpus. MSFT and NVDA aren't in the corpus.
> - Generation latency is derived, because the server doesn't send it.
> - Demo mode uses a real captured response.

---

Build a polished, production-quality web app called **"FinSight: Financial Evidence Engine"**. It's the front end for a live RAG system I built that answers questions over earnings-call transcripts (15,023 chunks, 76 tickers, 2019–2023) with **cited sources, conflict detection across calls, and honest abstention**. The audience is financial analysts and technical interviewers. It should feel like a premium research terminal (think Perplexity crossed with Bloomberg, with a clean modern look), not a chatbot demo.

## Stack
- React + Vite + TypeScript, Tailwind CSS, shadcn/ui, Recharts, lucide-react, Framer Motion, react-markdown.
- Dark theme by default (near-black #0A0E17, slate panels, amber #F59E0B accent for citations, emerald for "grounded," rose for "abstained or conflict"), with a light-mode toggle. Monospace (JetBrains Mono) for numbers, tickers and metrics.
- API base URL from `import.meta.env.VITE_API_URL`, defaulting to `https://finsight-api-995576020018.us-central1.run.app`. CORS is open, and the API is always on, so there's no cold start. All calls go through one `src/lib/api.ts`. If `GET /health` fails or times out (6 s), switch to **Demo mode** using the captured response in §5, with an amber "Demo mode" badge in the header.
- A Settings popover lets the user override the API URL at runtime (localStorage).
- Header links:
  - GitHub `https://github.com/aparmarthi/rag-hybrid-search-reranking-system`
  - Original Streamlit UI `https://finsight-ui-995576020018.us-central1.run.app`
  - API docs `{base}/docs`
  - W&B `https://wandb.ai/ameyparmarthi-finsight/finsight-biencoder-finetune`

## Backend API (live, verified; do not invent fields)
- `GET /health` returns `{status: "ok", qdrant_reachable: true, points_indexed: 15023, llm_gateway: "openrouter", llm_key_configured: true}`.
  - The header status dot is green when `qdrant_reachable && llm_key_configured`, with the label "15,023 chunks indexed" (use `points_indexed`).
  - If `llm_key_configured` is false, show amber "Retrieval only".
- `POST /query/stream` with body `{"question": string (3–1000 chars), "top_k": 5}` returns **Server-Sent Events over a POST**.
  - EventSource can't POST, so use `fetch` and parse the ReadableStream manually. Buffer partial chunks and split events on a blank line (`\n\n`). Each event has one `event:` line and one `data:` line containing JSON.
  - `event: token`, `data: {"text": "..."}`: append to the answer as it streams. The answer is **markdown** with `##` headings, bold and bullet lists, plus inline `[N]` citation markers.
  - `event: done`, `data:` an object with exactly these keys: `grounded` (bool), `routing_path` (string), `rewritten_query` (string), `staleness_flag` (bool), `temporal_reference` (`{year: number|null, quarter: number|null}`), `conflicts` (array, usually empty), `citations` (`[{chunk_number, source_label}]`), `chunks` (`[{chunk_id, ticker, doc_type, date, score, text}]`), `latency_ms` (int), `latency_per_node_ms`, `tokens` (`{input, output, cache_read}`).
  - `latency_per_node_ms` has the keys `query_understanding, router, retrieve, rerank, detect_conflicts`, in that order. It has no `generate` key.
  - `event: error`, `data: {"detail": "..."}`: show a friendly error toast and keep the question in the box.
- `POST /query` (non-streaming) returns the same fields plus `answer`, `cost_usd` and `failure_mode`. Use it for a "Run non-streaming (shows exact cost)" toggle.
- `GET /recommend/{ticker}?k=5` returns `{ticker, related: [{ticker, score}]}`. `related` is **empty for tickers not in the corpus**, in which case hide the chips.
- `POST /feedback` takes `{question, answer, rating: 1 | -1, note}`.

### Critical rules for citations and evidence
- **Citation `[N]` refers to `chunks[N-1]`.** The model sees the evidence numbered in exactly the order the server returns it.
  - **Never re-sort the `chunks` array.** Scores aren't monotonic, because the server applies a query-relative recency boost after reranking. Card N is labeled `[N]`.
  - Show `score` as a bar labeled "rerank score".
- `citations` lists only the chunk numbers the answer actually used. Cards that aren't cited get a muted "retrieved, not cited" style. Cited cards get an amber border and a count of how many times they're cited.
- `text` is an **excerpt: the server returns the first 600 characters of each chunk**, and the model saw the full chunk.
  - If `text.length === 600`, show "Excerpt — first 600 chars" with a tooltip: "The cited passage may appear later in this chunk."
  - If the backend later sends longer text, render all of it.
- `source_label` looks like `"AAPL earnings_transcript 2020-10-29"`. In the hover preview, render it as ticker badge + "Earnings call" + formatted date.

## Pages

### 1. Ask (main page, three-column layout on desktop)
- **Left: query history and example questions.** Store history in localStorage. The example chips are grouped and verified against the corpus:
  - *Grounded:*
    - "What did Apple say about iPhone supply chain in 2020?"
    - "What did companies say about COVID-19 supply chain disruptions?"
    - "Oracle cloud revenue growth"
    - "How did Tesla's Shanghai Model 3 margins compare to Model 3 margins produced in Fremont during Q1 2020?" (golden-set g002)
  - *Conflict check* (slower; runs the extraction node):
    - "Did company revenue guidance match actual results?"
    - "How did management revise its full-year outlook over the year?"
  - *Watch it refuse:*
    - "What did Apple say about iPhone sales in 2015?" (before the corpus)
    - "What is the current stock price of Tesla today?" (not a transcript)
    - "Should I buy or sell Nvidia stock?" (investment-advice guardrail)
- **Center: search bar and streamed answer.**
  - A big search bar (⌘K to focus) and the streamed markdown answer, with a typing cursor while tokens arrive.
  - Render inline `[N]` markers as small amber chips. Hovering a chip shows the source preview; clicking it scrolls to and pulses evidence card N.
- **Status badges above the answer:**
  - **Grounded** (emerald) or **Insufficient evidence** (rose). When `grounded` is false or the answer starts with "INSUFFICIENT EVIDENCE", show a dedicated, well-designed abstention state: "FinSight refuses to guess. The corpus covers 76 companies' earnings calls from 2019–2023; this question is outside it or the evidence is too thin."
  - The routing path chip (e.g. "earnings_analysis"), with a tooltip explaining the 3 paths.
  - "Rewritten as: …" (collapsible).
  - The temporal scope chip from `temporal_reference`, e.g. "Scope: 2020" or "Scope: Q2 2022". Hide it when both fields are null.
  - A **Stale evidence** amber warning when `staleness_flag` is true.
- **Conflicts panel** when `conflicts` is non-empty: side-by-side cards showing the contradicting statements and their sources. Render each conflict object's fields generically. When it's empty and the question had comparison/guidance intent, show a muted note:
  > "No conflicts found. The detector is precision-first and only flags paired guidance-vs-actual evidence."
- **Right: evidence cards** from `chunks`, in server order (see the rules above). Each card shows `[N]`, a ticker badge, date, doc type, the rerank score bar, a text snippet with expand, and the cited/not-cited styling.
- **Pipeline trace (below the answer):**
  - A horizontal waterfall of `latency_per_node_ms` in key order, plus a **derived `generate` bar = `latency_ms` − sum(node values)**, labeled "generate (derived)".
  - When `detect_conflicts` is 0, render it as a hatched "skipped — gated (no comparison intent)" segment. This is a cost-control design choice, so call it out.
  - Show total latency and time to first token, measured client-side from request start to the first `token` event.
  - Show tokens in/out. `cache_read` gets a small info icon: "0 by design: the system prompt is below Sonnet's 1,024-token cache minimum (DEC-018)."
  - Typical live numbers, for reference: query_understanding ~1.6 s, router ~0.8 s, retrieve ~0.4 s, rerank ~1.9 s, generate ~7–8 s; ~12–15 s total.
- **Cold-path UX:** generation dominates latency. While waiting for the first token, show a progress line that walks through the stages ("Understanding query → Routing → Retrieving → Reranking → Checking conflicts → Generating"), advancing on roughly those timings.
- **Feedback:** thumbs up/down with an optional note, sent to `/feedback`.
- **Related companies:** chips for the most-cited ticker via `/recommend/{ticker}`. Clicking one pre-fills "What did {TICKER} say about …". Hide the row when `related` is empty.
- **Cost:** in streaming mode, show "≈ $0.012–0.016 / query (measured)". In non-streaming mode, show the exact `cost_usd`.

### 2. Evaluation (static, embedded numbers in `src/data/evals.ts`)
- **KPI cards:**
  - **+27.4% NDCG@10**, hybrid + rerank vs dense-only (target ≥ 10% ✅)
  - **RAGAS faithfulness 0.806** (target ≥ 0.80 ✅; n = 40, Claude judge + Voyage embeddings)
  - **First token 4.3 s live**, full answer ~12–15 s (target P95 ≤ 3 s ❌)
  - **$0.0135 / query** mean (n = 5 live, range $0.012–0.015; target ≤ $0.005 ❌)
  - Show the target next to each with ✅/❌. **Don't hide the misses.** Add a "Why we missed" tooltip: "~3.2K tokens of retrieved evidence to Sonnet is the cost floor; generation, not hosting, is the latency bottleneck (DEC-018)."
- **Ablation 1, Retrieval** (n = 40 grounded queries, pooled-LLM relevance labels). Show it as a grouped bar chart (Recall@5, MRR, NDCG@10) plus a table:
  ```ts
  export const RETRIEVAL = [
    { config: "Dense only (voyage-finance-2)", recall5: 0.5782, mrr: 0.6518, ndcg10: 0.5835, p50ms: 148.1 },
    { config: "Hybrid (BM25 + dense, RRF)",    recall5: 0.6547, mrr: 0.7974, ndcg10: 0.7180, p50ms: 144.6 },
    { config: "Hybrid + Cohere Rerank",        recall5: 0.6503, mrr: 0.8040, ndcg10: 0.7434, p50ms: 282.9 },
  ]; // ndcg lift hybrid_rerank vs dense = +27.4%
  ```
  Insight callout:
  > "Hybrid alone captures most of the lift (NDCG 0.584 → 0.718). Reranking sharpens ordering (MRR 0.797 → 0.804, NDCG → 0.743) but slightly trades recall (0.655 → 0.650) and doubles retrieval latency (145 → 283 ms). It reorders the top set; it doesn't retrieve more."
- **Ablation 2, Chunking** (60-doc subset, n = 40):
  ```ts
  export const CHUNKING = [
    { strategy: "Fixed 400-token", recall5: 0.20, ndcg10: 0.1297 },
    { strategy: "Sentence-aware",  recall5: 0.20, ndcg10: 0.1100 },
    { strategy: "Paragraph",       recall5: 0.25, ndcg10: 0.1125 },
  ];
  ```
  Use an "Honest caveat" banner:
  > "Within noise at this subset size; absolute scores are low because the golden queries target the full corpus. A conclusive result needs a full-corpus re-index. Reported as-is, not cherry-picked."
  This setup differs from Ablation 1, so don't plot the two together.
- **Ablation 3, Bi-encoder fine-tune** (two-tower, bge-small-en-v1.5, MultipleNegativesRankingLoss, 48 leakage-guarded training pairs; eval on 40 held-out queries against a 3,000-chunk pool):
  - **Recall@5 rises from 0.825 to 0.870 (+4.5 pts mean, range +2.5 to +5.0, positive on all 5 seeds).** Show a 5-seed dot plot.
  - Link to W&B.
- **RAGAS detail card:** faithfulness 0.806 and answer_relevancy 0.20, with an explanation:
  > "Low answer_relevancy is the intended trade-off: answers deliberately hedge when evidence is thin ('the chunks confirm X but not Y'), which RAGAS scores as incomplete. Groundedness first."
- **Failure-mode taxonomy cards:** retrieval_miss, bad_ranking, hallucination, ambiguous_query, stale_data and none. Each gets a one-line definition and the fix it points to.
- **"What this can't prove yet" card:**
  - The golden set is small: 50 queries, made up of 40 grounded, 5 adversarial and 5 abstention.
  - The corpus covers a single domain.
  - Conflict detection rarely fires on standard retrieval, because it needs paired guidance-vs-actual evidence.
  - There has been no load test yet.
  - The Claude vs GPT-4o bake-off hasn't been run.

### 3. Architecture
- An interactive diagram of the 6-node LangGraph pipeline. Clicking a node opens a side sheet with what it does and the trade-off behind it:
  1. **Query understanding:** Haiku, forced tool call. Rewrites the query and extracts ticker/year/quarter; falls back to the raw query on failure.
  2. **Router:** Haiku, forced enum (earnings_analysis / financial_metrics / risk_and_events), with a safe default.
  3. **Hybrid retrieve:** native server-side BM25 + dense (voyage-finance-2) RRF in Qdrant, 20 candidates.
  4. **Rerank:** Cohere Rerank 3.5 (local ms-marco cross-encoder fallback) to 8, then a query-relative temporal boost ("recent" means close to the quarter the user asked about, not the newest document), a staleness flag, and a trim to 5.
  5. **Conflict detection:** only runs on comparison or guidance intents, because extraction costs ~14 s. It's precision-gated (rev > 3%, EPS > 5%, margin > 1pp, guidance > 2pp) and never blocks the answer.
  6. **Generate:** Sonnet via OpenRouter's Anthropic-compatible gateway. Uses numbered evidence only, inline [N] citations, an explicit abstention token, and no investment advice.
- **"Design decisions" list:**
  - Inline citations instead of a forced tool call. First token dropped from 11.6 s to ~1.2 s, because tool JSON is buffered (DEC-011).
  - A cheap model for routing and an expensive one for generation.
  - Gated conflict detection.
  - Query-relative recency (DEC-014).
  - The LLM gateway is a config switch: when credits ran out, one env var moved it to OpenRouter with no eval invalidation (DEC-018).
  - Always-on Cloud Run with secrets in Secret Manager under a least-privilege service account, and max-instances as an LLM-spend cap (DEC-019).
- **Business value card**, labeled "Model assumptions — see PRD §10":
  - About $12K/month of analyst time saved per seat (~3 hrs/day × $200/hr × 20 days).
  - At $500/seat/month, that's about a 24× ROI.
  - About $15/month in LLM cost per seat (≈ $0.015 × 50 queries/day × 20 days), which gives about a 97% gross margin.

## 4. Polish requirements
- **Footer disclaimer:** "Research tool over historical transcripts (2019–2023). Not investment advice."
- **Usability:**
  - Loading skeletons and empty states.
  - Keyboard shortcuts: ⌘K and Esc.
  - A copy-answer-with-citations button, which appends a sources list built from `citations`.
  - A share link that puts the question in a URL parameter (`?q=`) and auto-runs it.
- **Accessibility:** keyboard navigable, sufficient contrast, and an aria-live region for the streaming answer.
- **No secrets:** no API keys in the frontend. The backend holds all secrets.
- **No invented data:** no lorem ipsum and no invented metrics. If a number isn't in this prompt or the API response, don't show it.

## 5. Demo mode fixture (`src/data/demo.ts`): a real response captured from the live API
Question: "What did Apple say about iPhone supply chain in 2020?"

In demo mode, replay `answer` as fake token events (about 30 ms per word), then apply `done`:
```ts
export const DEMO = {
  answer: "## Apple iPhone Supply Chain Commentary – 2020\n\n**Supply Constraints (Q4 2020)**\n\nTim Cook confirmed Apple was supply constrained across multiple product lines in late 2020 [3]:\n- iPhone was constrained at the \"front end of the ramp\" following the later-than-usual iPhone 12 launch [3]\n- Supply constraints also affected Mac, iPad, and some Apple Watch models [3]\n- Orders for iPhone 12 mini and Pro Max had not yet been taken, adding further uncertainty [3]\n\n**Demand Context**\n\nPrior to mid-September 2020, Apple was seeing **double-digit growth** in iPhone customer demand [1]. Cook acknowledged COVID-19 likely dampened what could have been even stronger demand from a macro spending perspective [1].\n\n**COVID-19 Supply Chain Preparedness**\n\nIn response to potential second-wave disruptions, Apple took several measures [1]:\n- Converted stores into \"express storefronts\" to maintain sales while prioritizing safety [1]\n- Increased staffing on phone support channels [1]\n- Kept the online store fully operational throughout [1]\n\n**iPhone 12 Product Context**\n\nThe iPhone 12 lineup represented Apple's first 5G-enabled devices, featuring the A14 Bionic chip and new Ceramic Shield, described as Apple's \"most prolific product introduction period ever\" [5].",
  done: {
    grounded: true, routing_path: "earnings_analysis",
    rewritten_query: "Apple iPhone supply chain commentary and statements in 2020",
    staleness_flag: false, temporal_reference: { year: 2020, quarter: null }, conflicts: [],
    citations: [
      { chunk_number: 3, source_label: "AAPL earnings_transcript 2020-10-29" },
      { chunk_number: 1, source_label: "AAPL earnings_transcript 2020-10-29" },
      { chunk_number: 5, source_label: "AAPL earnings_transcript 2020-10-29" },
    ],
    chunks: [
      { chunk_id: "mf_AAPL_2020Q4_c14", ticker: "AAPL", doc_type: "earnings_transcript", date: "2020-10-29", score: 0.72,  text: "start off with the iPhone lineup here, particularly, as you mentioned, the carrier subsidies that you're seeing makes you optimistic about iPhone sales. I think just looking at some other factors here, earlier in the year, you had mentioned that iPhone sales w…" },
      { chunk_id: "mf_AAPL_2022Q2_c11", ticker: "AAPL", doc_type: "earnings_transcript", date: "2022-04-28", score: 0.745, text: "this point in the cycle. Thank you. Tim Cook -- Chief Executive Officer We were happy with the iPhone growth last quarter, particularly when you think about the comp that it was going against because we had very different timing on the launches in the year ago…" },
      { chunk_id: "mf_AAPL_2020Q4_c16", ticker: "AAPL", doc_type: "earnings_transcript", date: "2020-10-29", score: 0.635, text: "about it. We continue to be very enthusiastic about the whole payment services area. Apple Card is doing well, and Apple Pay is doing exceptionally well. As you can imagine, in this environment, people are -- less want to hand over a card, so this contactless…" },
      { chunk_id: "mf_AAPL_2022Q1_c13", ticker: "AAPL", doc_type: "earnings_transcript", date: "2022-01-27", score: 0.649, text: "lot of good there. And I would remind you that iPhone was constrained in the quarter. And so I'm not sure where the statements are coming around about inventory, and I can't comment on whether other people have more or not. I don't know the answer to that. Tha…" },
      { chunk_id: "mf_AAPL_2020Q4_c2",  ticker: "AAPL", doc_type: "earnings_transcript", date: "2020-10-29", score: 0.554, text: "it as a call to action. We have seen the pain in our communities. Many of us have seen our children work hard to adapt to remote learning. And we all know that the road ahead is uncertain. This quarter and throughout the year, our response to this crisis has b…" },
    ],
    latency_ms: 12561,
    latency_per_node_ms: { query_understanding: 1612, router: 832, retrieve: 388, rerank: 1934, detect_conflicts: 0 },
    tokens: { input: 3247, output: 313, cache_read: 0 },
  },
};
```
Mark the excerpts in demo mode as "Excerpt", the same way as in live mode.
