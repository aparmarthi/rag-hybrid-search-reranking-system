# Bolt.new prompt: FinSight UI

Paste everything below the line into bolt.new.

---

Build a polished, production-quality web app called **"FinSight: Financial Evidence Engine"**. It's the front end for a live RAG system I built that answers questions over earnings-call transcripts (15,023 chunks, 76 tickers, 2019–2023) with **cited sources, conflict detection across calls, and honest abstention**. The audience is financial analysts and technical interviewers. It should feel like a premium research terminal (think Perplexity crossed with Bloomberg, with a clean modern look), not a chatbot demo.

## Stack
- React + Vite + TypeScript, Tailwind CSS, shadcn/ui, Recharts, lucide-react, Framer Motion, react-markdown.
- Dark theme by default (near-black #0A0E17, slate panels, amber #F59E0B accent for citations, emerald for "grounded," rose for "abstained or conflict"), with a light-mode toggle. Monospace (JetBrains Mono) for numbers, tickers and metrics.
- API base URL from `import.meta.env.VITE_API_URL` (default `https://finsight-api-995576020018.us-central1.run.app`). All calls go through one `api.ts`. If the API is unreachable, switch to "Demo mode" with one canned example response (badged in the header).

## Backend API (already live, do not change it)
- `GET /health` → `{status, qdrant_reachable, points_indexed, llm_gateway, llm_key_configured}`. Drives a header status dot that shows "15,023 chunks indexed."
- `POST /query/stream` with body `{"question": string (3–1000 chars), "top_k": 5}` returns **Server-Sent Events over a POST**. EventSource can't do POST, so use `fetch` and parse the ReadableStream manually. Events are separated by a blank line, each with `event:` and `data:` lines:
  - `event: token`, `data: {"text": "..."}`: append to the answer as it streams.
  - `event: done`, `data: {grounded, routing_path, rewritten_query, staleness_flag, temporal_reference, conflicts: [...], citations: [{chunk_number, source_label}], chunks: [{chunk_id, ticker, doc_type, date, score, text}], latency_ms, latency_per_node_ms: {nodeName: ms}, tokens: {input, output, cache_read}}`
  - `event: error`, `data: {"detail": "..."}`: show a friendly error toast and keep the question.
- `POST /query` (non-streaming) returns the same fields plus `answer`, `cost_usd`, `failure_mode`. Use it for a "Run as batch / show cost" debug toggle.
- `GET /recommend/{ticker}?k=5` → `{ticker, related: [{ticker, score}]}`.
- `POST /feedback` with `{question, answer, rating: 1 | -1, note}`.

## Pages

1. **Ask (main page, three-column layout on desktop)**
   - Left: query history (localStorage) and example question chips, e.g. "What did Apple say about iPhone supply chain in 2020?", "How did Microsoft describe Azure growth in Q2 2022?", "Did NVIDIA raise or lower data center guidance in 2023?", "What risks did Tesla highlight about production in 2021?"
   - Center: a big search bar (⌘K to focus) and the streamed answer, with a typing cursor while tokens arrive. Render inline citation markers like `[1]` and `[2]` as small amber chips. Hovering a chip shows the source preview; clicking scrolls to and pulses the matching evidence card.
   - Status badges above the answer: **Grounded** (emerald) or **Insufficient evidence** (rose; when the answer starts with "INSUFFICIENT EVIDENCE", render a dedicated, well-designed abstention state explaining that the system refuses to guess); the routing path (e.g. "earnings_analysis"); "Rewritten as: …" (collapsible); a **Stale evidence** amber warning when `staleness_flag` is true, showing `temporal_reference`.
   - A **Conflicts panel** when `conflicts` is non-empty: side-by-side cards showing the contradicting statements and their sources. Render each conflict object's fields generically.
   - Right: **Evidence cards** (from `chunks`) ranked by rerank score, with a ticker badge, date, doc type, a score bar, text snippet with expand, and highlighting when cited.
   - Below the answer: a **Pipeline trace** waterfall chart from `latency_per_node_ms` (render whatever node keys arrive, in order), total latency, time to first token (measure client-side from request start to first token event), and a token breakdown including cache-read tokens.
   - Thumbs up/down feedback with an optional note → `/feedback`.
   - "Related companies" chips for the top cited ticker via `/recommend/{ticker}`. Clicking one pre-fills a question.

2. **Evaluation (static, embedded numbers)**
   - KPI cards: **+27% NDCG@10** for hybrid + rerank vs. dense-only; **RAGAS faithfulness 0.81** (n = 40 golden set); typical TTFT ≈ 4.3 s with streaming; ~$0.0135 per query.
   - Retrieval ablation bar chart: Dense-only (baseline = 1.00), Hybrid, Hybrid + Rerank (+27%). Leave clearly marked placeholders for the exact intermediate values: `// TODO: fill from evals/`.
   - Failure-mode taxonomy cards: retrieval_miss, bad_ranking, hallucination, ambiguous_query, stale_data, none, each with a one-line definition and the fix it points to.
   - "What this can't prove yet" card: small golden set, single-domain corpus.

3. **Architecture**
   - An interactive diagram of the 6-node LangGraph pipeline. Clicking a node opens a side sheet with what it does and the trade-off behind it:
     1. Query understanding: Haiku, forced tool call; rewrites the query and extracts ticker/year/quarter; falls back to the raw query on failure.
     2. Router: Haiku, forced enum (earnings_analysis / financial_metrics / risk_and_events), with a safe default.
     3. Hybrid retrieve: dense + BM25, 20 candidates.
     4. Rerank: cross-encoder to 8, then a query-relative temporal boost ("recent" means close to the quarter the user asked about, not the newest document), a staleness flag, and a trim to 5.
     5. Conflict detection: only runs on comparison or guidance intents, because it costs ~14 s; never blocks the answer.
     6. Generate: Sonnet, numbered evidence only, inline [N] citations, an explicit abstention token, no investment advice, a cached system prompt.
   - A "Design decisions" list: inline citations instead of a structured citation tool (first token ~11 s → ~1 s, because tool JSON is buffered); a cheap model for routing and an expensive one for generation; gated conflict detection; query-relative recency.

## Polish requirements
- Disclaimer in the footer: "Research tool over historical transcripts (2019–2023). Not investment advice."
- Cold-start handling: if the first token takes more than 3 s, show a progress line that walks through the pipeline stages ("Understanding query → Routing → Retrieving → Reranking → Checking conflicts → Generating").
- Loading skeletons, empty states, keyboard shortcuts (⌘K, Esc), copy-answer-with-citations button, share link (question in a URL param that auto-runs).
- Accessibility: keyboard navigable, sufficient contrast, aria-live region for the streaming answer.
- No API keys in the frontend. The backend holds all secrets.
