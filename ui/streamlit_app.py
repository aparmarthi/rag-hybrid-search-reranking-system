"""
FinSight Streamlit demo — 5-tab multi-scenario (v2.3 Week 4).

Tabs:
    1. Ask            — streamed, cited Q&A over the earnings-call corpus
    2. Conflict       — the differentiator: guidance-vs-actual contradiction demo
    3. Related tickers — recommendation layer (shared embedding infra)
    4. Observability  — per-query cost, latency, routing, failure mode
    5. Business value — the ROI / who-is-this-for framing

Thin HTTP client over the FastAPI backend (same API that's deployed + load-tested).

Run:
    streamlit run ui/streamlit_app.py     (needs the API on $API_URL)
"""
from __future__ import annotations

import json
import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="FinSight", page_icon="📊", layout="wide")
st.title("📊 FinSight")
st.caption(
    "Multi-source financial evidence engine — grounded, cited answers over "
    "earnings-call transcripts. Knows what it doesn't know: refuses when it can't "
    "ground an answer, flags stale evidence, and surfaces contradictions."
)


# ----- Shared: stream a query, return the final `done` payload (or None) -----
def stream_query(question: str, top_k: int, answer_box) -> dict | None:
    done, text = None, ""
    try:
        with httpx.stream("POST", f"{API_URL}/query/stream",
                          json={"question": question, "top_k": top_k}, timeout=120) as resp:
            resp.raise_for_status()
            event = None
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line.split(":", 1)[1])
                    if event == "token":
                        text += payload["text"]
                        answer_box.markdown(text + "▌")
                    elif event == "done":
                        done = payload
    except Exception as e:  # noqa: BLE001
        answer_box.error(f"Query failed: {e}")
        return None
    answer_box.markdown(text)
    return done


def render_result(done: dict) -> None:
    """Render badges, conflicts, citations, metrics, evidence from a `done` payload."""
    cols = st.columns(3)
    cols[0].success("Grounded ✓") if done.get("grounded") else cols[0].warning("Abstained")
    if done.get("routing_path"):
        cols[1].info(f"Path: {done['routing_path']}")
    if done.get("staleness_flag"):
        cols[2].warning("⏳ Stale evidence")

    conflicts = done.get("conflicts", [])
    if conflicts:
        st.markdown("### ⚠️ Evidence conflicts detected")
        for c in conflicts:
            st.error(f"**{c['metric']}** ({c.get('subject', '')}): {c['explanation']}")

    if done.get("citations"):
        st.markdown("### Citations")
        for c in done["citations"]:
            st.markdown(f"- **[{c['chunk_number']}]** {c['source_label']}")

    m = st.columns(4)
    m[0].metric("Latency", f"{done.get('latency_ms', 0)} ms")
    m[1].metric("Output tokens", done.get("tokens", {}).get("output", 0))
    m[2].metric("Est. cost", f"${done.get('cost_usd', 0):.4f}" if done.get("cost_usd") else "—")
    m[3].metric("Conflicts", len(conflicts))

    if done.get("chunks"):
        st.markdown("### Retrieved evidence")
        for i, ch in enumerate(done["chunks"], 1):
            with st.expander(f"[{i}] {ch['ticker']} · {ch['doc_type']} · {ch['date']} · score={ch['score']}"):
                st.write(ch["text"])


# ----- Sidebar: health -----
with st.sidebar:
    st.header("System")
    try:
        h = httpx.get(f"{API_URL}/health", timeout=5).json()
        if h.get("qdrant_reachable"):
            st.success(f"API healthy · {h.get('points_indexed', 0):,} chunks")
        else:
            st.warning("API degraded")
    except Exception as e:  # noqa: BLE001
        st.error(f"API unreachable at {API_URL}")
        st.caption(str(e)[:150])
    top_k = st.slider("Chunks to retrieve", 3, 15, 5)
    st.divider()
    st.caption("Hybrid BM25+dense (voyage-finance-2) → Cohere rerank → Claude Sonnet · "
               "LangGraph 6-node pipeline · conflict detection")


tab_ask, tab_conflict, tab_recs, tab_obs, tab_value = st.tabs(
    ["🔍 Ask", "⚠️ Conflict detector", "🔗 Related tickers", "📈 Observability", "💵 Business value"]
)

# ---- Tab 1: Ask ----
with tab_ask:
    q = st.text_input("Ask about the earnings calls",
                      placeholder="What did companies say about COVID-19 supply chain disruptions?")
    if st.button("Search", type="primary", key="ask") and q.strip():
        st.markdown("### Answer")
        done = stream_query(q, top_k, st.empty())
        if done:
            render_result(done)

# ---- Tab 2: Conflict detector (the differentiator) ----
with tab_conflict:
    st.markdown("**Surfaces contradictions instead of averaging them.** Ask a "
                "guidance/comparison question — the detector flags numeric claims that disagree "
                "(guidance vs actual, cross-quarter drift).")
    examples = [
        "Did company revenue guidance match actual results?",
        "How did management revise its full-year outlook over the year?",
        "Compare guided vs reported margins across quarters",
    ]
    cq = st.selectbox("Try a conflict-oriented query", examples)
    custom = st.text_input("…or your own (include words like 'guidance', 'versus', 'revised')")
    query = custom.strip() or cq
    if st.button("Detect conflicts", type="primary", key="conflict"):
        st.markdown("### Answer")
        done = stream_query(query, max(top_k, 8), st.empty())
        if done:
            render_result(done)
            if not done.get("conflicts"):
                st.info("No conflicts surfaced in the retrieved evidence for this query. "
                        "(The detector fires only on genuine cross-call numeric contradictions.)")

# ---- Tab 3: Related tickers (recommendation layer) ----
with tab_recs:
    st.markdown("**Recommendation on shared infrastructure.** Related tickers come from "
                "cosine-nearest-neighbor over the *same* voyage-finance-2 vectors that power "
                "retrieval — retrieval and recommendation are the same problem.")
    ticker = st.text_input("Ticker", value="AAPL").strip().upper()
    if st.button("Find related tickers", type="primary", key="recs") and ticker:
        try:
            r = httpx.get(f"{API_URL}/recommend/{ticker}", params={"k": 6}, timeout=15).json()
            rel = r.get("related", [])
            if rel:
                st.markdown(f"### Tickers most similar to **{ticker}** (by earnings-call language)")
                for item in rel:
                    st.markdown(f"- **{item['ticker']}** · similarity {item['score']:.3f}")
            else:
                st.warning(f"{ticker} not in the corpus universe.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Recommendation failed: {e}")

# ---- Tab 4: Observability ----
with tab_obs:
    st.markdown("**Every query is measured.** Run one to see per-query cost, latency, "
                "the routing path, and the failure-mode classification.")
    oq = st.text_input("Query to trace", placeholder="Microsoft cloud revenue growth",
                       key="obs_q")
    if st.button("Run + trace", type="primary", key="obs") and oq.strip():
        try:
            d = httpx.post(f"{API_URL}/query", json={"question": oq, "top_k": top_k}, timeout=120).json()
            c = st.columns(4)
            c[0].metric("Total latency", f"{d.get('latency_ms', 0)} ms")
            c[1].metric("Est. cost", f"${d.get('cost_usd', 0):.4f}" if d.get("cost_usd") else "—")
            c[2].metric("Routing path", d.get("routing_path", "—"))
            c[3].metric("Failure mode", d.get("failure_mode", "—"))
            if d.get("latency_per_node_ms"):
                st.markdown("**Per-node latency (the cost-routing story — cheap Haiku, one Sonnet call):**")
                st.json(d["latency_per_node_ms"])
            st.markdown("**Tokens:**")
            st.json(d.get("tokens", {}))
        except Exception as e:  # noqa: BLE001
            st.error(f"Trace failed: {e}")

# ---- Tab 5: Business value ----
with tab_value:
    st.markdown("""
### Who it's for & why it matters

**Target user:** institutional equity analysts at sub-$1B AUM funds who can't afford
Bloomberg ($24K/seat) or AlphaSense ($15K/seat), yet must cross-reference earnings
calls, filings, and market data under earnings-season time pressure.

**The value:**
- ~3 hrs/day saved cross-referencing sources → **~$12K/month** of analyst time per seat
- Priced at **$500/mo** (≈2.5% of a Bloomberg Terminal) → **~24× ROI** at point of sale
- Unit economics: ~$0.005/query × ~50 queries/day → **~99% gross margin**

**Why the design choices matter to a regulated buyer (SEC Rule 10b-5):**
a confident-but-wrong number is worse than a refusal — so the trust gates *are*
the product: grounded citations on every claim, honest abstention, conflict
surfacing, and staleness flags.

*Full model in `docs/PRD.md` §10.*
""")
