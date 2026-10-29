FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY embedding_service /app/embedding_service
RUN useradd -u 1000 -m inference
USER inference
ENV PATH="/app/.venv/bin:$PATH" OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
CMD ["uvicorn", "embedding_service.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
