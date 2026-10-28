# DiffMind PR reviewer

Self-hosted GitHub reviews with mandatory hybrid repository retrieval and DeepSeek.
n8n receives signed GitHub events and schedules a small Python worker. PostgreSQL
holds durable jobs; Qdrant holds revision-scoped code vectors. No GPU is required.

## What it does

- Reviews opened, reopened, ready-for-review and updated PRs. Drafts are skipped.
- Publishes inline comments at valid diff lines, evidence links, optional single-line
  suggestions, and one maintained summary per PR.
- Reviews changes since the last successfully published commit; falls back to a full
  PR diff when history diverges. Manual full reviews are supported.
- Requires exact identifier, BM25 and dense retrieval before the model can review.
  Search failures fail the job rather than silently dropping repository context.
- Uses Tree-sitter boundaries plus bounded line windows, local BGE-small embeddings,
  identifier splitting, reciprocal rank fusion and a second DeepSeek verification pass.
- Scopes every Qdrant query to repository and immutable head SHA. Indexes complete
  snapshots, caches embeddings by content, and retains the latest three snapshots
  plus the previous/current review heads. This favors consistency over an overlay index.
- Deduplicates webhook deliveries, supersedes stale queued work, serializes indexing,
  fences publication with leases/head checks, and reconciles timed-out GitHub writes.
- Never imports, installs or executes the reviewed repository's code.

PR commands (repository write permission required): `/diffmind review`,
`/diffmind full-review`, `/diffmind pause`, `/diffmind resume`.

## Run locally

Install Python 3.12 and uv, then:

```sh
uv sync --frozen
docker compose -p diffmind-tests -f compose.test.yaml up -d
uv run pytest -q
uv run ruff check diffmind tests
```

The integration tests use real PostgreSQL and Qdrant and download the embedding
models on first run. Unit tests alone: `uv run pytest -q -m 'not integration'`.
Tests do not call DeepSeek or write to GitHub.

## Deploy

See [deployment/README.md](deployment/README.md) for secrets, n8n workflows,
GitHub permissions, resource limits and rollback. Start with a single allowlisted
repository. The DeepSeek API is paid; the worker, database, vector search and
embedding model run on your own server.

Repository rules are read from the PR's target branch, never from unmerged code:

```json
{"exclude": ["fixtures/*", "generated/*"], "instructions": "All money values are integer cents."}
```

Save this as `.diffmind.json`. Rules cannot enable code execution.

## Current limits

This is a tested first version, not full CodeRabbit parity. It does not execute
tests or static-analysis tools, automatically resolve discussions, chat in review
threads, learn from feedback, or open fix PRs. The secret filter covers selected
key patterns and filenames, not a comprehensive secret scanner. Relevant code
and PR text are sent to the configured DeepSeek API.

Large files, oversized lines, source/index budgets and oversized diffs produce
partial-coverage notices. A single oversized file diff is skipped rather than
split across reviews. Maximum five accepted findings per run, twelve model
batches, one active job, two CPU cores and 2 GiB per worker/Qdrant container by
default. Large-repository latency and peak memory still require workload testing.
Git object and embedding caches persist; monitor disk usage and maintain backups.

## Synthetic application

This repository contains synthetic code for testing an automated pull-request reviewer.
Deliberately faulty examples belong on labelled test PRs, not on the default branch.
No production data or credentials belong here.

The sample ledger uses integer cents and requires positive amounts. Refunds cannot
exceed the captured payment. Authorization belongs at the service boundary.

Run the sample tests with `python -m unittest discover -s tests_sample`.
