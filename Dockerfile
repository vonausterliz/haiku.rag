# Immagine dell'app RAG: solo codice e dipendenze. Dati, config e cache modelli vivono in /data (bind mount).
FROM python:3.12-slim-bookworm

# Librerie di sistema per opencv/docling (rendering PDF, OCR)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=600 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dipendenze prima del codice: layer in cache finché uv.lock non cambia
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY docker/default.haiku.rag.yaml /app/default.haiku.rag.yaml
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev && chmod +x /usr/local/bin/entrypoint.sh

RUN useradd --create-home --uid 1000 rag
USER rag

ENV DATA_DIR=/data \
    HAIKU_RAG_CONFIG_PATH=/data/config/haiku.rag.yaml \
    HF_HOME=/data/cache/huggingface \
    OMP_NUM_THREADS=2

VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -fs http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "haiku_local_rag.main:app", "--host", "0.0.0.0", "--port", "8000"]
