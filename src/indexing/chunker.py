"""
Chunking strategies for FinSight text corpora.

Three strategies (Week 3 ablation story):
    1. fixed_400     — fixed-size token windows with 50-token overlap
    2. sentence      — sentence-aware, greedy up to max_tokens
    3. paragraph     — paragraph-aware, respects blank-line separators

Per-corpus tuning (this is the interview signal):
    - earnings transcripts: paragraph strategy preserves speaker turns + Q&A pairs
    - 10-K Item 1A risk factors: paragraph strategy preserves bullet risk items
    - 8-K material events: fixed_400 since short and structured
    - 10-Q MD&A: sentence strategy for long flowing narrative

Token counting uses simple whitespace heuristic (1 word ≈ 1.3 tokens).
Close enough for 400-token targets; exact counts matter only at embedding time.

Usage:
    from src.indexing.chunker import chunk_text, ChunkStrategy
    chunks = chunk_text(text, strategy="paragraph", max_tokens=400, overlap_tokens=50)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ChunkStrategy = Literal["fixed_400", "sentence", "paragraph"]


@dataclass
class Chunk:
    text: str
    chunk_index: int
    token_count: int


def _estimate_tokens(text: str) -> int:
    """Whitespace-count heuristic. 1 word ≈ 1.3 tokens."""
    return int(len(text.split()) * 1.3)


def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter — good enough for 400-token chunks."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines (two+ newlines)."""
    paragraphs = re.split(r"\n\s*\n+", text)
    return [p.strip() for p in paragraphs if p.strip()]


def _chunk_fixed(text: str, max_tokens: int, overlap_tokens: int) -> list[Chunk]:
    """
    Token-window chunking with overlap. Operates on whitespace-split words.
    max_tokens is the target; we cut at word boundaries just past that.
    """
    words = text.split()
    # Approximate: target N tokens ≈ N/1.3 words
    words_per_chunk = max(1, int(max_tokens / 1.3))
    overlap_words = max(0, int(overlap_tokens / 1.3))
    step = max(1, words_per_chunk - overlap_words)

    chunks: list[Chunk] = []
    i = 0
    idx = 0
    while i < len(words):
        window = words[i : i + words_per_chunk]
        if not window:
            break
        chunk_text = " ".join(window)
        chunks.append(Chunk(text=chunk_text, chunk_index=idx, token_count=_estimate_tokens(chunk_text)))
        idx += 1
        i += step
    return chunks


def _chunk_greedy(units: list[str], max_tokens: int) -> list[Chunk]:
    """
    Greedy packing: accumulate units (sentences or paragraphs) until adding the
    next one would exceed max_tokens. Emits current chunk and starts fresh.
    """
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    idx = 0

    for unit in units:
        unit_tokens = _estimate_tokens(unit)

        # Single unit too big? Emit whatever we have, then the oversized unit as its own chunk.
        if unit_tokens > max_tokens:
            if current:
                text = " ".join(current) if not current[0].endswith("\n") else "\n\n".join(current)
                chunks.append(Chunk(text=text, chunk_index=idx, token_count=current_tokens))
                idx += 1
                current = []
                current_tokens = 0
            # Fall back to fixed chunking for the oversized unit
            for sub in _chunk_fixed(unit, max_tokens, overlap_tokens=0):
                chunks.append(Chunk(text=sub.text, chunk_index=idx, token_count=sub.token_count))
                idx += 1
            continue

        if current_tokens + unit_tokens > max_tokens and current:
            text = " ".join(current)
            chunks.append(Chunk(text=text, chunk_index=idx, token_count=current_tokens))
            idx += 1
            current = []
            current_tokens = 0

        current.append(unit)
        current_tokens += unit_tokens

    if current:
        text = " ".join(current)
        chunks.append(Chunk(text=text, chunk_index=idx, token_count=current_tokens))

    return chunks


def chunk_text(
    text: str,
    strategy: ChunkStrategy = "paragraph",
    max_tokens: int = 400,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """
    Chunk `text` using the given strategy.

    Args:
        text: raw text to chunk.
        strategy: 'fixed_400' | 'sentence' | 'paragraph'.
        max_tokens: target chunk size. Default 400.
        overlap_tokens: only applies to 'fixed_400'. Default 50.

    Returns:
        List of Chunk objects.
    """
    text = text.strip()
    if not text:
        return []

    if strategy == "fixed_400":
        return _chunk_fixed(text, max_tokens, overlap_tokens)
    if strategy == "sentence":
        return _chunk_greedy(_split_sentences(text), max_tokens)
    if strategy == "paragraph":
        return _chunk_greedy(_split_paragraphs(text), max_tokens)
    raise ValueError(f"Unknown chunking strategy: {strategy}")
