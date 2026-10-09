FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-serve.txt .
RUN pip install --upgrade pip && pip install -r requirements-serve.txt

# Bake the BM25 model into the image: runtime downloads from Cloud Run hit HuggingFace's
# anonymous 429 rate limit, which crashed hybrid retrieval on fresh instances.
ENV FASTEMBED_CACHE_PATH=/app/.cache/fastembed
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding(model_name='Qdrant/bm25')"

COPY src/ ./src/
COPY api/ ./api/
COPY ui/ ./ui/
# ticker_centroids.npz: without it /recommend rebuilds from a full Qdrant scan per cold start
COPY artifacts/ ./artifacts/

RUN useradd --create-home --uid 1000 finsight && chown -R finsight:finsight /app
USER finsight

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
