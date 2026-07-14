# LinkedIn Copy — FinSight launch

Drafts to adapt to your voice. Pick one main post; the Featured section holds the live URL + video + blog. Edit the bracketed bits. Post after the demo video is recorded and the blog is published (so the links are live).

---

## Option A — the "differentiator" angle (recommended)

> Most RAG demos answer a question and stop. In financial research, the hard part is what happens when your sources **disagree**.
>
> I built **FinSight** — a RAG system over 15,000 earnings-call transcripts that does three things most don't:
>
> 🔹 **Cites every claim** back to a specific transcript — no citation, no claim
> 🔹 **Flags contradictions** between sources instead of averaging them into a confident, wrong answer (a company guides to 15%, reports 9% — it catches that)
> 🔹 **Refuses to guess** — when it can't ground an answer, it says so
>
> The engineering that mattered wasn't building the conflict detector — it was making it *stop crying wolf*. Four classes of false positive, each a domain lesson: guidance ranges aren't conflicts, a quarter isn't a full year, "revenue" isn't one number.
>
> Measured, not vibes: hybrid + reranking beat plain semantic search by **27% NDCG** on a 50-query benchmark; faithfulness passed at **0.81**.
>
> Stack: hybrid BM25+dense (Qdrant RRF) → Cohere rerank → 6-node LangGraph pipeline → Claude, with per-node cost routing.
>
> 🔗 Live demo, code, and a write-up on killing the false positives — in the comments / Featured.
>
> #RAG #LLM #AIEngineering #MLOps #fintech

---

## Option B — the "career transition" angle (more personal)

> I lead AI deployments for a living — the strategy layer between a customer's problem and the solution. To go deeper on the *engineering* side, I've been building production-grade ML systems end to end.
>
> Latest: **FinSight**, a financial-research RAG system with a feature most RAG demos skip — it surfaces when sources **contradict each other** instead of smoothing it over, and it refuses to answer when it can't ground the claim.
>
> What I took away: the demo is the easy part. Earning the right to *trust* the output — killing false positives, measuring retrieval quality (+27% NDCG over the baseline), gating on faithfulness (0.81) — that's the actual work, and it's the same discipline I bring to real customer deployments.
>
> Live demo + code + technical write-up below.
>
> #AI #RAG #LLM #ProductManagement #MachineLearning

---

## Option C — short/punchy (text post, no article)

> Built a financial-research RAG that does what most don't: it flags when two sources **disagree** (guidance vs. actual), cites every claim, and refuses to guess when the evidence isn't there.
>
> Hardest part wasn't the feature — it was killing the false positives (a guidance *range* isn't a conflict; a quarter isn't a year).
>
> +27% NDCG over baseline retrieval, 0.81 faithfulness. Live demo + code 👇
>
> #RAG #LLM #AIEngineering

---

## Featured section (3 items, in this order)
1. **Loom video** — "FinSight: financial RAG with conflict detection (90-sec demo)"
2. **Live demo** — https://finsight-ui-z0mp.onrender.com
3. **Blog post** — [your published URL]  •  **Code** — https://github.com/aparmarthi/rag-hybrid-search-reranking-system

## Posting notes (delete before posting)
- **Don't post until the demo works live** (needs credit) and the video/blog are up — dead links on a launch post are the worst first impression.
- Put links in a **first comment**, not the post body, if you want max reach (LinkedIn suppresses posts with external links) — or in Featured.
- Tag/skills to check: keep hashtags to ~3-5.
- Option A leads with the product/differentiator; Option B leads with your PM→engineering story. Given your target (AI PM / SA / FDE), **B** may resonate most with hiring managers, **A** with engineers. Pick by audience, or run B now and A later.
