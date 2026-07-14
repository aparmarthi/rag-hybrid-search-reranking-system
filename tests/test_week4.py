"""
Week-4 unit tests — cost tracking, failure classification, feedback endpoint.
No API calls (config uses CI dummy keys); pure logic + FastAPI TestClient.
"""
from __future__ import annotations


# ---- Cost tracker ----
def test_cost_estimate_sonnet():
    from src.utils.cost_tracker import estimate_cost
    # 1M in + 1M out on sonnet-4-6 ($3 + $15) = $18
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000) == 18.0


def test_cost_cache_read_discount():
    from src.utils.cost_tracker import estimate_cost
    full = estimate_cost("claude-sonnet-4-6", 1_000_000, 0)
    cached = estimate_cost("claude-sonnet-4-6", 1_000_000, 0, cache_read_tokens=1_000_000)
    assert cached < full  # cache reads billed at ~10% of input


def test_query_cost_includes_retrieval_surcharge():
    from src.utils.cost_tracker import query_cost
    c = query_cost({"input": 0, "output": 0, "cache_read": 0}, "claude-sonnet-4-6")
    assert c > 0  # retrieval surcharge applies even with zero LLM tokens


def test_haiku_cheaper_than_sonnet():
    from src.utils.cost_tracker import estimate_cost
    h = estimate_cost("claude-haiku-4-5", 100_000, 10_000)
    s = estimate_cost("claude-sonnet-4-6", 100_000, 10_000)
    assert h < s  # the cost-routing premise


# ---- Failure classifier ----
class _Chunk:
    def __init__(self, score):
        self.score = score


def test_failure_retrieval_miss_on_empty():
    from src.utils.failure_tracker import FailureMode, classify
    assert classify({"reranked": []}) == FailureMode.RETRIEVAL_MISS


def test_failure_none_on_healthy():
    from src.utils.failure_tracker import FailureMode, classify
    state = {"reranked": [_Chunk(0.8)], "grounded": True, "answer": "x", "rewritten_query": "q"}
    assert classify(state) == FailureMode.NONE


def test_failure_stale_flag():
    from src.utils.failure_tracker import FailureMode, classify
    state = {"reranked": [_Chunk(0.8)], "grounded": True, "answer": "x",
             "rewritten_query": "q", "staleness_flag": True}
    assert classify(state) == FailureMode.STALE_DATA


def test_failure_hallucination_when_ungrounded_but_answered():
    from src.utils.failure_tracker import FailureMode, classify
    state = {"reranked": [_Chunk(0.8)], "grounded": False,
             "answer": "Confident wrong answer", "rewritten_query": "q"}
    assert classify(state) == FailureMode.HALLUCINATION


def test_failure_abstain_is_not_hallucination():
    from src.utils.failure_tracker import FailureMode, classify
    state = {"reranked": [_Chunk(0.8)], "grounded": False,
             "answer": "INSUFFICIENT EVIDENCE: not covered", "rewritten_query": "q"}
    assert classify(state) != FailureMode.HALLUCINATION


# ---- Feedback endpoint (TestClient, no LLM) ----
def test_feedback_endpoint_records():
    from fastapi.testclient import TestClient

    from api.main import app
    client = TestClient(app)
    r = client.post("/feedback", json={"question": "q", "answer": "a", "rating": 1})
    assert r.status_code == 200
    assert r.json()["status"] == "recorded"


def test_feedback_rejects_bad_rating():
    from fastapi.testclient import TestClient

    from api.main import app
    client = TestClient(app)
    r = client.post("/feedback", json={"question": "q", "rating": 5})  # out of [-1,1]
    assert r.status_code == 422  # pydantic validation
