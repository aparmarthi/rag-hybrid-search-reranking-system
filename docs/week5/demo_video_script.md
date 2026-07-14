# FinSight — 90-Second Loom Demo Script

Paint-by-numbers recording plan. **Prereqs before you hit record:**
1. Anthropic credit topped up (the pipeline must actually answer — it's down on empty credit).
2. Open the live UI: https://finsight-ui-z0mp.onrender.com — **and run one throwaway query first** to warm the free-tier dyno (else the first real query cold-starts ~50s on camera).
3. Have the tabs ready: Ask, Conflict detector, Related tickers.
4. Loom set to screen + mic (optionally camera bubble).

Target: **~90 seconds.** Tight. Narration is written to be read at a natural pace — trim if you run long. Times are cumulative.

---

### [0:00–0:12] Hook + what it is
**Screen:** FinSight UI, top of the Ask tab.
**Say:**
> "This is FinSight — a financial-research RAG system over 15,000 earnings-call transcripts. What makes it different isn't that it answers questions — it's that it refuses to make things up, and it flags when sources contradict each other. Let me show you."

### [0:12–0:35] Grounded, cited answer
**Screen:** Ask tab. Type: *"What did companies say about COVID-19 supply chain disruptions?"* → Search. Let it stream.
**Say (while it streams):**
> "Every answer streams token-by-token, and every claim is cited back to a specific transcript — ticker, date, the exact chunk. No citation, no claim. Under the hood it's hybrid search — keyword plus semantic — reranked, then Claude generates only from the retrieved evidence."

**Screen:** scroll to show the Citations list + one expanded evidence chunk.

### [0:35–0:58] The differentiator — conflict detection
**Screen:** switch to the **Conflict detector** tab. Pick the guidance example → Detect conflicts.
**Say:**
> "Here's the part most RAG systems don't do. Financial sources disagree constantly — a company guides to one number, then reports another. Instead of averaging that into a confident, wrong answer, FinSight surfaces the contradiction — the metric, the two values, and the periods. It's precision-tuned: it stays silent unless there's a genuine cross-call conflict, because a detector that cries wolf is worse than none."

*(If the conflict panel fires, point at it. If it doesn't for your query, say: "It only fires on real contradictions in the retrieved evidence — here it correctly stays quiet," and pivot to the abstention point below. Do NOT fake it.)*

### [0:58–1:12] Knows what it doesn't know
**Screen:** Ask tab. Type something out-of-range: *"What did Apple say about iPhone sales in 2015?"* → Search.
**Say:**
> "And when it can't ground an answer — here, a year before my data starts — it says so instead of hallucinating. That honesty is the whole point for a regulated user, where a confident wrong number is worse than 'I don't know.'"

### [1:12–1:25] Proof + stack (fast)
**Screen:** Observability tab (show cost/latency/routing), or the README ablation table.
**Say:**
> "It's measured, not vibes: on a 50-query benchmark, hybrid-plus-reranking beat plain semantic search by 27% on ranking quality, and faithfulness passed at 0.81. Full architecture, ablations, and decision log are on GitHub."

### [1:25–1:30] Close
**Say:**
> "That's FinSight — grounded, cited, and honest about its limits. Links below."

---

## Fallback if the live demo is flaky on the day
Record against **localhost** instead (same UI, `streamlit run ui/streamlit_app.py` with the API running locally) — identical experience, no cold-start, and you control it. Just don't show the URL bar if it says localhost, or note "running locally" honestly.

## The 3 links to put in the Loom description / LinkedIn
- Live demo: https://finsight-ui-z0mp.onrender.com
- Code: https://github.com/aparmarthi/rag-hybrid-search-reranking-system
- Blog post: [your published URL]

## One honest note
The conflict detector's live firing depends on retrieval surfacing both halves of a conflict — it's reliable on paired evidence but not guaranteed on every query (documented limitation). For the video, either (a) pre-test a query where it fires and use that, or (b) narrate the precision-first framing and let it correctly stay silent. Both are honest; a rigged always-fires demo is not.
