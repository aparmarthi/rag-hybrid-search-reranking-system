"""
FinSight centralized configuration.

Pattern: single Settings class, loaded once from .env + environment.
Import `settings` anywhere. Never read os.getenv() directly elsewhere.

Example:
    from src.utils.config import settings
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Loads from .env at repo root. Missing required keys raise at import time."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- LLM APIs -----
    anthropic_api_key: SecretStr = Field(..., description="Anthropic Claude API key")
    openai_api_key: SecretStr | None = Field(None, description="OpenAI key — Week 3 eval only")

    # ----- Embeddings -----
    voyage_api_key: SecretStr = Field(..., description="Voyage AI for voyage-finance-2 embeddings")

    # ----- Reranker -----
    cohere_api_key: SecretStr = Field(..., description="Cohere Rerank 3.5 reranker API")

    # ----- Vector store -----
    qdrant_url: str = Field("http://localhost:6333", description="Qdrant endpoint. Blank for local.")
    qdrant_api_key: SecretStr | None = Field(None, description="Qdrant Cloud key; None for local")

    # ----- Observability -----
    langsmith_api_key: SecretStr = Field(..., description="LangSmith tracing")
    langsmith_tracing: bool = Field(True)
    langsmith_project: str = Field("finsight-dev")

    # ----- Model selection -----
    anthropic_primary_model: str = Field("claude-sonnet-4-6")
    anthropic_router_model: str = Field("claude-haiku-4-5-20251001")
    voyage_model: str = Field("voyage-finance-2")
    cohere_rerank_model: str = Field("rerank-english-v3.5")

    # ----- App config -----
    env: str = Field("development")
    log_level: str = Field("INFO")
    max_chunks_returned: int = Field(5)
    recency_boost_quarters: int = Field(2)
    recency_boost_weight: float = Field(0.15)

    # ----- DuckDB -----
    duckdb_path: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "processed" / "finsight.duckdb")

    # ----- Cost controls -----
    max_cost_per_query_usd: float = Field(0.05, description="hard cap guardrail")
    daily_api_budget_usd: float = Field(10.0, description="circuit breaker during dev")

    # ----- Paths (derived, not env-configurable) -----
    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def data_raw(self) -> Path:
        return REPO_ROOT / "data" / "raw"

    @property
    def data_processed(self) -> Path:
        return REPO_ROOT / "data" / "processed"

    @property
    def artifacts_dir(self) -> Path:
        return REPO_ROOT / "artifacts"

    @property
    def ticker_universe_path(self) -> Path:
        return self.artifacts_dir / "ticker_universe.json"

    @property
    def motley_fool_pkl(self) -> Path:
        return self.data_raw / "motley_fool" / "motley-fool-data.pkl"

    @property
    def sec_edgar_dir(self) -> Path:
        return self.data_raw / "sec_edgar"

    @property
    def ohlcv_dir(self) -> Path:
        return self.data_raw / "ohlcv" / "stocks"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
