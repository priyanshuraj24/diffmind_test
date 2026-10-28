FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY diffmind ./diffmind
RUN uv sync --frozen --no-dev && useradd -u 1000 -m worker && mkdir /data && chown worker:worker /data
USER worker
ENV PATH="/app/.venv/bin:$PATH" OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
EXPOSE 8000
CMD ["uvicorn", "diffmind.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
