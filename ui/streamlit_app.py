"""
FinSight Streamlit demo.

Week 1: single query box → grounded cited answer + evidence chunks + metrics.
Week 4 expands to the 5-tab multi-scenario demo (earnings / metrics / conflict /
context / business value).

Talks to the FastAPI backend via HTTP so the UI stays a thin client (the same
API that gets load-tested and deployed).

Run:
    streamlit run ui/streamlit_app.py
Requires the API running:
    uvicorn api.main:app --port 8000
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
    "earnings call transcripts. Every claim traces to a source."
)

# ----- Sidebar: health + settings -----
with st.sidebar:
    st.header("System")
    try:
        health = httpx.get(f"{API_URL}/health", timeout=5).json()
        if health.get("qdrant_reachable"):
            st.success(f"API healthy · {health.get('points_indexed', 0):,} chunks indexed")
        else:
            st.warning("API degraded — Qdrant unreachable")
    except Exception as e:  # noqa: BLE001
        st.error(f"API unreachable at {API_URL}")
        st.caption(str(e)[:200])

    top_k = st.slider("Chunks to retrieve", min_value=3, max_value=15, value=5)
    st.divider()
    st.caption("Week 1 · dense retrieval (bge-m3) + Claude Sonnet with structured citations")


# ----- Main: query -----
example = "What did companies say about COVID-19 supply chain disruptions?"
question = st.text_input("Ask a question about the earnings calls", value="", placeholder=example)

if st.button("Search", type="primary") and question.strip():
    st.markdown("### Answer")
    answer_box = st.empty()
    done = None
    text_so_far = ""

    try:
        with httpx.stream(
            "POST",
            f"{API_URL}/query/stream",
            json={"question": question, "top_k": top_k},
            timeout=90,
        ) as resp:
            resp.raise_for_status()
            event = None
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    payload = json.loads(line.split(":", 1)[1])
                    if event == "token":
                        text_so_far += payload["text"]
                        answer_box.markdown(text_so_far + "▌")  # cursor while streaming
                    elif event == "done":
                        done = payload
    except Exception as e:  # noqa: BLE001
        st.error(f"Query failed: {e}")
        st.stop()

    answer_box.markdown(text_so_far)  # final, no cursor

    if done is None:
        st.warning("Stream ended without a final result.")
        st.stop()

    if done["grounded"]:
        st.success("Grounded ✓")
    else:
        st.warning("Abstained — evidence did not support a confident answer")

    # Citations
    if done["citations"]:
        st.markdown("### Citations")
        for c in done["citations"]:
            st.markdown(f"- **[{c['chunk_number']}]** {c['source_label']}")

    # Metrics row
    m1, m2, m3 = st.columns(3)
    m1.metric("Latency", f"{done['latency_ms']} ms")
    m2.metric("Output tokens", done["tokens"]["output"])
    m3.metric("Cache-read tokens", done["tokens"]["cache_read"])

    # Evidence chunks
    st.markdown("### Retrieved evidence")
    for i, chunk in enumerate(done["chunks"], 1):
        header = f"[{i}] {chunk['ticker']} · {chunk['doc_type']} · {chunk['date']} · score={chunk['score']}"
        with st.expander(header):
            st.write(chunk["text"])
