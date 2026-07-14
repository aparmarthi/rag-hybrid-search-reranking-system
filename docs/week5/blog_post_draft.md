# Building an Evidence Conflict Detector for Financial RAG — and the False Positives I Had to Kill

*Draft — edit for your voice before publishing (Medium / LinkedIn article / personal site). Everything below is grounded in the real build; swap the bracketed bits and cut freely.*

---

Most RAG demos answer a question and stop. The interesting problem in financial research isn't answering — it's what happens when your sources **disagree**. Management guides to 15% growth on the Q2 earnings call; the Q3 call reports 9%. A good analyst catches that. A naive RAG system averages it into a confident, wrong sentence.

I built **FinSight**, a RAG system over ~15,000 earnings-call transcript chunks (76 tickers, 2019–2023), with a feature most RAG systems don't have: an **evidence conflict detector** that surfaces contradictions instead of smoothing them over. This post is about the part that actually took the work — not building the detector, but making it *stop crying wolf*.

## The easy 80%: extract claims, compare them

The engine is two steps:

1. **Extract** — one Claude call over the retrieved evidence pulls out structured numeric claims: `{metric, subject, value, period, is_guidance, source_chunk}`. Financial numbers live in prose ("services revenue was about $19.8 billion, up 17%"), so an LLM extractor beats regex here.
2. **Compare** — pairwise, flag any two same-metric claims that diverge beyond a per-metric threshold (revenue >3%, EPS >5%, guidance >2pp).

I wired it up, ran it on a guidance query, and got **6 conflicts**. Great — except most of them were garbage.

## The hard 20%: every false positive was a lesson

I didn't trust the 6 conflicts, so I printed the underlying claims. Each false positive turned out to be a distinct *class* of error, and killing each one taught me something about the domain:

**1. Guidance ranges.** "Third quarter revenue in the range of down 15% to down 18%" got extracted as two claims — "-15%" and "-18%" — which the comparator flagged as a 3-point conflict. But that's *one coherent statement*, not a contradiction.
→ **Gate:** the two claims must come from **different chunks**. Two numbers in one sentence are almost never a real conflict.

**2. Quarter vs. full-year.** "Q3 margin 18.5%" vs "FY margin 21%" — flagged as a 2.5pp conflict. But a single quarter and a full year aren't the same scope; comparing them is meaningless.
→ **Gate:** claims must have **comparable periods** — same period, or a guidance→actual pair for that period. A quarter vs. a year is neither.

**3. Different segments, same metric label.** "Products revenue +8%" vs "Services +17%" — same call, both tagged `growth_rate`, flagged as a 9-point conflict. They're just *different line items*.
→ **Gate:** I added a `subject` field to each claim ("Products", "Services", "iPhone") and required **subject match**. Same metric ≠ same thing.

**4. Same-call figures.** Even after the above, two numbers from the *same* earnings call were getting compared. But a genuine conflict is guidance in one quarter vs. the actual reported in a *later* call.
→ **Gate:** the two chunks must be from **different dates**.

After four gates, the noisy query returned **zero** conflicts — and a constructed genuine case (a company that guided 15% for Q3 and delivered 9%) fired correctly, while a control (two different segments both at similar rates) stayed silent.

## The honest limitation I chose to document, not hide

Here's the part I'd want an interviewer to push on: the detector is *correct*, but its **live recall is limited by retrieval**. Standard retrieval doesn't reliably fetch *both halves* of a conflict pair — the guidance chunk AND the later-actual chunk — into the same result set. So the engine detects conflicts reliably when the evidence is paired; live queries surface them less often than the engine can catch.

I could have hidden that. Instead I documented it as the next unlock (a conflict-oriented retrieval mode that deliberately fetches a ticker's guidance plus its subsequent actuals). "The detector is right; the retrieval that feeds it needs a conflict-aware mode" is a more honest — and more useful — statement than a demo rigged to always fire.

## Why precision-first was the right call

A conflict detector that fires often but wrongly is *worse than none* — it trains the analyst to ignore it. I optimized for precision: it fires rarely, but when it does, it's a real guidance-vs-actual contradiction with the numbers and periods attached. In a regulated setting (SEC Rule 10b-5 liability on any numeric claim), a false "these disagree" is its own kind of hallucination.

## The stack, briefly

Hybrid BM25 + dense retrieval (voyage-finance-2) with native Qdrant RRF fusion → Cohere reranking → a 6-node LangGraph pipeline → Claude for generation with inline citations. On a 50-query golden set, hybrid+rerank beat dense-only retrieval by **+27% NDCG@10**, and RAGAS faithfulness came in at **0.81** (clearing the 0.80 gate I'd set). The conflict detector rides on top of that.

## Takeaway

The lesson that generalized beyond this project: **in LLM systems, the demo is the easy part; earning the right to trust the output is the work.** Every false positive I killed was a domain insight in disguise — ranges aren't conflicts, scopes must match, "revenue" isn't one number. That's the difference between a RAG demo and a RAG *product*.

*Code + live demo: [github.com/aparmarthi/rag-hybrid-search-reranking-system](https://github.com/aparmarthi/rag-hybrid-search-reranking-system)*

---

### Editing notes (delete before publishing)
- **Verify the live conflict demo works** before claiming it in the post — needs Anthropic credit + a query where both halves are retrieved. If it doesn't reliably fire live, keep the post's honest framing (the limitation section already covers this — don't overclaim the live demo).
- Numbers used: +27% NDCG@10, faithfulness 0.81, ~15K chunks / 76 tickers / 2019-2023. All real (evals/results/).
- Consider a screenshot of the conflict panel or the ablation table.
- Length is ~900 words — good for LinkedIn article / Medium. Trim the stack paragraph if posting as a shorter LinkedIn text post.
