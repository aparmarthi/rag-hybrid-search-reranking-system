# FinSight: Financial Evidence Engine (frontend)

A research-terminal UI for the FinSight RAG API: 15,023 earnings-call chunks across 76 tickers (2019-2023).
Every claim in an answer is a numbered citation that links to the exact evidence chunk.

## Features

| Page | What it shows |
| --- | --- |
| **Ask** | Streaming answers (SSE over POST), `[N]` citations mapped 1:1 to `chunks[N-1]`, rerank-score bars, per-node pipeline trace, conflict and abstention states, related companies, export, `?q=` deep links, `j`/`k` evidence navigation |
| **Architecture** | LangGraph pipeline with the model used at each node, key design decisions from [`docs/decisions.md`](../docs/decisions.md), stack and rationale |
| **Evaluation** | Live behavioral eval suite (9 cases: grounded, conflict, refuse + citation-integrity check), production telemetry, offline benchmark and retrieval ablation |

If `/health` fails or times out, the app switches to **demo mode** with captured responses so it never shows a blank screen.

## Run locally

```bash
cd frontend
cp .env.example .env   # all values optional
npm ci
npm run dev
```

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Vite dev server |
| `npm test` | Vitest unit tests (SSE parser, citation helpers, eval scoring) |
| `npm run typecheck` | TypeScript strict check |
| `npm run build` | Production build to `dist/` |
| `npm run lint` | ESLint |

## Project layout

```
src/
  lib/
    api.ts            typed API client + streaming SSE parser
    evidence.ts       citation parsing/linking, abstention detection, formatting
    eval-suite.ts     eval cases, per-case scoring, run summary (p50/p95, cost)
    telemetry.ts      fire-and-forget query + error reporting, summary fetch
    project-facts.ts  offline metrics and decision log (sourced from this repo)
    demo.ts           captured responses for demo mode
  hooks/              query runner, eval runner, API health, history, theme
  components/finsight/  page and panel components
```

## Telemetry

The app posts to the API's `/telemetry/query` and `/telemetry/error` (stored in Postgres, DEC-024). Per live query it records outcome
(grounded / abstained / error / cancelled), routing path, time to first token, total latency, chunk count,
tokens and cost. Uncaught errors (React error boundary, `window.onerror`, unhandled rejections) are also recorded.

- **Privacy:** question text and personal data are never stored. Session IDs are random per tab.
- **Security:** the browser holds no database credential. The API validates every field (Pydantic bounds that
  mirror the schema's CHECK constraints) and rate-limits writes per IP. The dashboard reads
  `GET /telemetry/summary`, which returns aggregates only.
- Demo-mode traffic is recorded but excluded from the summary.

## Deploy

Static build: any static host works (Vercel, Netlify, Cloud Storage + CDN). Set the env vars above at build time.

```bash
npm run build   # outputs dist/
```

The API must allow the frontend origin via CORS.
