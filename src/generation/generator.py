"""
Answer generation with Claude Sonnet + inline-citation parsing.

Week 1 baseline: dense-retrieved chunks → Sonnet 4.6 → grounded answer where
every claim carries an inline [N] citation to a source chunk. We parse those
[N] markers into structured Citation objects mapped to the source chunk — this
gives grounded, traceable citations AND sub-second first-token streaming.

Design note (why inline [N] rather than forced tool-use):
    An earlier version enforced citations via a required `emit_answer` tool with
    a Pydantic schema. That guarantees structure but defeats streaming — with
    forced tool_choice, Claude buffers the entire tool-input JSON before emitting
    anything, so first-token latency was ~11s. Plain-text streaming gives a
    ~1s first token (v2.3's "first token < 500ms feels fast" principle). Inline
    [N] markers keep citations structured and parseable without the streaming
    penalty. See docs/decisions.md.

Prompt caching: the system prompt is stable across queries and carries a
cache_control breakpoint. (Week 1 prompt is below Sonnet's 2048-token cache
minimum, so it won't cache yet — see DEC-008 note. The Week 2 LangGraph prompt
clears the threshold.)

Usage:
    from src.generation.generator import Generator
    from src.retrieval.retriever import Retriever

    chunks = Retriever().search("What did Apple say about iPhone margins?")
    answer = Generator().generate("What did Apple say about iPhone margins?", chunks)
    print(answer.answer_text)
    for c in answer.citations:
        print(c.chunk_number, "->", c.source_label)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterator

import anthropic

from src.retrieval.retriever import RetrievedChunk
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


SYSTEM_PROMPT = """You are FinSight, a financial research assistant for equity analysts.

You answer questions using ONLY the numbered evidence chunks provided in the user \
message. Every factual or numeric claim MUST carry an inline citation to the chunk \
it came from, written as [N] where N is the chunk number.

Rules:
- Cite every factual or numeric claim inline with [N] (e.g. "revenue grew 17% [3]").
- Ground every claim in the provided evidence. Do not use outside knowledge.
- If the evidence does not contain the answer, say so plainly and abstain — do not \
guess. Begin your answer with "INSUFFICIENT EVIDENCE:" if the chunks do not support \
a confident answer.
- Never give buy/sell/hold investment advice.
- Be concise and factual. Analysts want evidence, not prose. Aim for under 200 words."""


@dataclass
class Citation:
    chunk_number: int
    source_label: str  # e.g. "AAPL earnings_transcript 2020-01-28"
    chunk_id: str | None = None


@dataclass
class GeneratedAnswer:
    answer_text: str
    citations: list[Citation]
    grounded: bool
    chunks_used: list[RetrievedChunk] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    # Pin to Anthropic's public API. Ignore any ambient ANTHROPIC_BASE_URL
    # (e.g. a corporate model-gateway proxy) so this personal project always
    # talks directly to Anthropic with the .env key. Use certifi's CA bundle
    # so TLS verifies regardless of the shell's SSL_CERT_FILE (Homebrew Python
    # ships without a system trust store). See DEC-010.
    import certifi
    import httpx

    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        base_url="https://api.anthropic.com",
        http_client=httpx.Client(verify=certifi.where()),
    )


def _format_evidence(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as a numbered evidence block for the prompt."""
    lines = []
    for i, c in enumerate(chunks, 1):
        src = f"{c.ticker or '?'} {c.doc_type or '?'}"
        if c.date:
            src += f" {c.date}"
        lines.append(f"[{i}] ({src})\n{c.text}")
    return "\n\n".join(lines)


def _source_label(chunk: RetrievedChunk) -> str:
    parts = [chunk.ticker or "?", chunk.doc_type or "?"]
    if chunk.date:
        parts.append(str(chunk.date))
    return " ".join(parts)


def _parse_citations(text: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    """Extract unique [N] markers from the answer, mapped to source chunks."""
    seen: dict[int, Citation] = {}
    for m in re.finditer(r"\[(\d+)\]", text):
        n = int(m.group(1))
        if n in seen or not (1 <= n <= len(chunks)):
            continue
        chunk = chunks[n - 1]
        seen[n] = Citation(chunk_number=n, source_label=_source_label(chunk), chunk_id=chunk.chunk_id)
    return list(seen.values())


def _build_user_content(query: str, chunks: list[RetrievedChunk]) -> str:
    return (
        f"Question: {query}\n\n"
        f"Evidence chunks:\n\n{_format_evidence(chunks)}\n\n"
        f"Answer using only these chunks. Cite every claim inline with [N]."
    )


def _no_evidence() -> GeneratedAnswer:
    return GeneratedAnswer(
        answer_text="No relevant evidence was retrieved for this question.",
        citations=[],
        grounded=False,
    )


class Generator:
    """Claude Sonnet generation with inline [N] citations + streaming support."""

    def __init__(self) -> None:
        self._client = _client()
        self._model = settings.anthropic_primary_model

    def generate(self, query: str, chunks: list[RetrievedChunk]) -> GeneratedAnswer:
        """Non-streaming: full grounded answer with parsed citations."""
        if not chunks:
            return _no_evidence()

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _build_user_content(query, chunks)}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return self._assemble(text, chunks, response.usage)

    def generate_stream(self, query: str, chunks: list[RetrievedChunk]) -> Iterator[dict]:
        """
        Stream the answer. Yields:
            {"type": "token", "text": "..."}             — incremental answer text
            {"type": "done", "answer": GeneratedAnswer}  — final structured result

        First token lands in ~1s (v2.3 UX principle). Citations are parsed from
        the completed [N] markers once the stream finishes.
        """
        if not chunks:
            yield {"type": "done", "answer": _no_evidence()}
            return

        parts: list[str] = []
        with self._client.messages.stream(
            model=self._model,
            max_tokens=1024,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _build_user_content(query, chunks)}],
        ) as stream:
            for text in stream.text_stream:
                parts.append(text)
                yield {"type": "token", "text": text}
            final = stream.get_final_message()

        full = "".join(parts)
        yield {"type": "done", "answer": self._assemble(full, chunks, final.usage)}

    def _assemble(self, text: str, chunks: list[RetrievedChunk], usage) -> GeneratedAnswer:
        """Build a GeneratedAnswer from the model's text + usage."""
        grounded = not text.strip().upper().startswith("INSUFFICIENT EVIDENCE")
        return GeneratedAnswer(
            answer_text=text,
            citations=_parse_citations(text, chunks),
            grounded=grounded,
            chunks_used=chunks,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
        )
