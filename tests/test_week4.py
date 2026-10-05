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


# ---- LLM gateway + graceful degradation (DEC-018) ----
def _provider_error():
    import anthropic
    import httpx
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))


def test_cost_prices_openrouter_model_ids():
    from src.utils.cost_tracker import estimate_cost
    assert estimate_cost("anthropic/claude-sonnet-4.6", 1_000_000, 0) == 3.0
    assert estimate_cost("anthropic/claude-haiku-4.5", 1_000_000, 0) == 1.0


def test_openrouter_gateway_requires_key(monkeypatch):
    import pytest

    from src.utils import llm_client
    monkeypatch.setattr(llm_client.settings, "llm_gateway", "openrouter")
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", None)
    llm_client.anthropic_client.cache_clear()
    with pytest.raises(llm_client.LLMConfigError, match="OPENROUTER_API_KEY"):
        llm_client.anthropic_client()
    llm_client.anthropic_client.cache_clear()


def test_query_returns_503_on_llm_provider_error(monkeypatch):
    from fastapi.testclient import TestClient

    import src.retrieval.graph as graph
    from api.main import app

    def boom(*args, **kwargs):
        raise _provider_error()
    monkeypatch.setattr(graph, "run_pipeline", boom)
    r = TestClient(app).post("/query", json={"question": "What did Apple say?"})
    assert r.status_code == 503
    assert "temporarily unavailable" in r.json()["detail"]


def test_stream_emits_error_event_on_llm_provider_error(monkeypatch):
    from fastapi.testclient import TestClient

    import src.retrieval.nodes as nodes
    from api.main import app

    def boom(state):
        raise _provider_error()
    monkeypatch.setattr(nodes, "query_understanding", boom)
    r = TestClient(app).post("/query/stream", json={"question": "What did Apple say?"})
    assert r.status_code == 200
    assert "event: error" in r.text


def test_health_reports_missing_llm_key(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app
    from src.utils import llm_client
    monkeypatch.setattr(llm_client.settings, "llm_gateway", "openrouter")
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", None)
    body = TestClient(app).get("/health").json()
    assert body["llm_gateway"] == "openrouter"
    assert body["llm_key_configured"] is False
    assert body["status"] == "degraded"


def test_query_returns_503_on_missing_llm_key(monkeypatch):
    from fastapi.testclient import TestClient

    import src.retrieval.graph as graph
    from api.main import app
    from src.utils.llm_client import LLMConfigError

    def boom(*args, **kwargs):
        raise LLMConfigError("LLM_GATEWAY=openrouter but OPENROUTER_API_KEY is not set")
    monkeypatch.setattr(graph, "run_pipeline", boom)
    assert TestClient(app).post("/query", json={"question": "What did Apple say?"}).status_code == 503
