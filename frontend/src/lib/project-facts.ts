// Sourced from the repository README and docs/decisions.md. Update when those change.

export const DECISIONS_URL = 'https://github.com/aparmarthi/rag-hybrid-search-reranking-system/blob/main/docs/decisions.md';

export interface Decision {
  id: string;
  title: string;
  decision: string;
  tradeoff: string;
}

export const DECISIONS: Decision[] = [
  {
    id: 'DEC-011',
    title: 'Inline [N] citations over forced tool use',
    decision:
      'Forced tool-use citations buffered the whole answer: 11.6 s to first token. Streaming plain text with inline [N] markers, parsed afterward, brought it to 1.3 s with the same source mapping (a Week 1 figure; live end-to-end TTFT through the full pipeline is 3.6 s median, measured 2026-10-16).',
    tradeoff: 'Gives up schema-enforced citations for a streaming UX; mitigated by post-hoc parsing and validation.',
  },
  {
    id: 'DEC-007',
    title: 'Precision-gated conflict detector',
    decision:
      'Naive numeric comparison produced false positives. Four gates (different chunks, comparable periods, matching subject, different call dates) removed each class, verified against a constructed NVDA guidance conflict and a control.',
    tradeoff: 'The extraction call adds ~25 s live, so it only runs on comparison intent. Retrieval does not always fetch both halves of a conflict.',
  },
  {
    id: 'DEC-014',
    title: 'Query-relative recency, not "newest"',
    decision:
      'On a 2019–2023 corpus, boosting the newest chunks hurts a Q1 2020 question. Rerank boosts by proximity to the period the question asks about, and flags staleness when the corpus cannot cover it.',
    tradeoff: 'Depends on the router extracting the period; failure degrades safely to pure relevance.',
  },
  {
    id: 'DEC-013',
    title: 'Native server-side hybrid search',
    decision:
      'Qdrant fuses BM25 and dense voyage-finance-2 legs with RRF in one query: no client-side fusion, no second round trip. Haiku handles understanding and routing; only generation uses Sonnet.',
    tradeoff: 'Linear pipeline for now; per-path retrieval branching waits on SEC data ingestion.',
  },
  {
    id: 'DEC-006',
    title: 'Managed rerank with a degradation chain',
    decision:
      'Cohere rerank-v3.5 primary, local ms-marco cross-encoder on any Cohere error, raw retrieval order as the last resort. The fallback fired live during a model-name bug and reranked correctly.',
    tradeoff: 'External dependency on the hot path, accepted because the fallback is tested.',
  },
  {
    id: 'DEC-002',
    title: 'Qdrant over Pinecone, Weaviate, FAISS, pgvector',
    decision:
      'Native hybrid in one query, the fastest metadata pre-filtering, and a free cloud tier for an always-available demo. pgvector was competitive but lacked native BM25 fusion.',
    tradeoff: 'At very large scale a serverless managed store has a cleaner ops story. Not this scale.',
  },
  {
    id: 'DEC-018',
    title: 'LLM gateway as a config switch',
    decision:
      'When the direct Anthropic key ran dry, the same SDK was pointed at OpenRouter\u2019s Anthropic-compatible endpoint by config. Provider errors now return a clear 503 instead of an opaque 500.',
    tradeoff: 'Kept Claude rather than switching models, because every measured eval number was produced with Claude.',
  },
  {
    id: 'DEC-019',
    title: 'Always-on Cloud Run for the live demo',
    decision:
      'Free-tier cold starts were ~51 s, which is what a hiring manager saw first. Moved to Cloud Run with min-instances=1, Secret Manager, a dedicated service account, and max-instances=2 to cap LLM spend.',
    tradeoff: 'Small standing cost in exchange for zero cold start and real logs.',
  },
];

export interface EvalMetric {
  label: string;
  target: string;
  measured: string;
  met: boolean;
  note: string;
}

export const OFFLINE_METRICS: EvalMetric[] = [
  { label: 'Faithfulness (RAGAS)', target: '≥ 0.80', measured: '0.806', met: true, note: 'n=40, Claude judge + Voyage embeddings' },
  { label: 'NDCG@10 lift vs dense', target: '≥ 10%', measured: '+27.4%', met: true, note: 'Hybrid + rerank vs dense only, n=40' },
  { label: 'Latency', target: 'P95 ≤ 3 s', measured: '3.6 s TTFT', met: false, note: 'Live median, n=4 (3.4–3.9 s). Full answer ~11 s; conflict queries ~34–36 s' },
  { label: 'Cost per query', target: '≤ $0.005', measured: '$0.0139', met: false, note: 'Mean, n=9 live (2026-10-16); ~3.2K evidence tokens to Sonnet is the floor' },
];

export const RETRIEVAL_ABLATION = [
  { config: 'Dense only (voyage-finance-2)', recall5: 0.578, mrr: 0.652, ndcg10: 0.584, p50ms: 148 },
  { config: 'Hybrid (BM25 + dense RRF)', recall5: 0.655, mrr: 0.797, ndcg10: 0.718, p50ms: 145 },
  { config: 'Hybrid + Cohere rerank', recall5: 0.65, mrr: 0.804, ndcg10: 0.743, p50ms: 283 },
];

export const FINETUNE_RESULT = {
  before: 0.825,
  after: 0.87,
  note: 'Two-tower bi-encoder fine-tune, Recall@5 on 40 held-out golden queries; positive on all 5 seeds (+2.5 to +5.0 pts).',
};

export const STACK = [
  { layer: 'Orchestration', choice: 'LangGraph', why: 'Stateful 6-node graph with per-node tracing' },
  { layer: 'Generation', choice: 'Claude Sonnet 4.6', why: 'Best citation-format adherence' },
  { layer: 'Routing & rewrite', choice: 'Claude Haiku 4.5', why: '~10× cheaper for classification' },
  { layer: 'Vector store', choice: 'Qdrant', why: 'Native BM25 + dense RRF in one query' },
  { layer: 'Embeddings', choice: 'voyage-finance-2', why: 'Domain-pretrained on financial text' },
  { layer: 'Reranker', choice: 'Cohere rerank-v3.5', why: 'Managed cross-encoder, local fallback' },
  { layer: 'API', choice: 'FastAPI (async)', why: 'Pydantic validation, SSE streaming' },
  { layer: 'Evals', choice: 'RAGAS + pytest', why: 'Faithfulness gate at 0.80' },
  { layer: 'Tracing', choice: 'LangSmith + W&B Weave', why: 'Per-node spans' },
  { layer: 'Deploy', choice: 'Cloud Run + Secret Manager', why: 'Always on, no cold start' },
  { layer: 'CI', choice: 'GitHub Actions', why: 'Lint, import guard, tests' },
  { layer: 'Frontend', choice: 'React + TypeScript', why: 'This interface' },
];
