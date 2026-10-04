"""
Shared Claude client for every serving-path call site (generator, router nodes, conflict detector).

The gateway is a config switch, not a second code path: both options speak the Anthropic
Messages API, so tool use, streaming, and cache_control behave identically. See DEC-010 / DEC-018.
"""
from __future__ import annotations

from functools import lru_cache

import anthropic
import certifi
import httpx

from src.utils.config import settings

_BASE_URLS = {
    "anthropic": "https://api.anthropic.com",
    "openrouter": "https://openrouter.ai/api",  # Anthropic-compatible; SDK appends /v1/messages
}


@lru_cache(maxsize=1)
def anthropic_client() -> anthropic.Anthropic:
    """Return the Claude client for the configured gateway.

    The base URL is pinned in code so an ambient ANTHROPIC_BASE_URL (e.g. a corporate
    model-gateway proxy) can never intercept calls. certifi's CA bundle keeps TLS
    verification working under Homebrew Python, which ships without a system trust store.

    Raises:
        ValueError: unknown gateway, or openrouter selected without OPENROUTER_API_KEY.
    """
    gateway = settings.llm_gateway.lower()
    if gateway not in _BASE_URLS:
        raise ValueError(f"LLM_GATEWAY must be one of {sorted(_BASE_URLS)}, got '{gateway}'")
    if gateway == "openrouter":
        if settings.openrouter_api_key is None:
            raise ValueError("LLM_GATEWAY=openrouter but OPENROUTER_API_KEY is not set")
        key = settings.openrouter_api_key.get_secret_value()
    else:
        key = settings.anthropic_api_key.get_secret_value()

    return anthropic.Anthropic(
        api_key=key,
        base_url=_BASE_URLS[gateway],
        http_client=httpx.Client(verify=certifi.where()),
    )
