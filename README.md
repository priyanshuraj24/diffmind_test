# DiffMind: visible n8n PR reviews

The complete review flow runs in n8n: GitHub intake, Git fetch and diff parsing,
source chunking, embedding requests, hybrid search, DeepSeek review and verification,
inline comments, summary updates, retries and revision retention. Open any node to
inspect its input, output and implementation. There is no remote review worker.

The original [PR Review Bot](https://n8n.weberaai.com/workflow/q4ifTzOOrmBYZlXE)
contains 75 nodes in 10 groups. Its existing production webhook URL now enters the
rebuilt flow. The old forwarding workflows and temporary test workflow are inactive.

## Flow

1. Verify GitHub's signature and deduplicate events in PostgreSQL.
2. Claim one durable job, obtain an App installation token, and check the PR head.
3. Fetch immutable Git commits asynchronously so n8n's runner remains responsive, without checking out or executing repository code.
4. Read trusted target-branch rules; parse full or incremental diffs and tracked blobs.
5. Chunk source using function-boundary heuristics, line windows and a complete-input byte bound.
6. Reuse a verified index for the same revision, or call dense/BM25 embedding nodes in 128-input transport batches, map vectors with native Edit Fields, and verify the Qdrant count.
7. Run semantic, lexical and exact-symbol searches, scoped to repository and head SHA.
8. Fuse rankings and reserve evidence for each changed file.
9. Ask DeepSeek to draft and independently verify findings; validate lines and citations.
10. Persist publication intent, reconcile bot comments, recheck the head, and publish.
11. Maintain one summary, save review state, and retain three revision indexes.

Qdrant and PostgreSQL are self-hosted. A small FastEmbed service provides only model
inference: BGE-small dense vectors and BM25 sparse vectors. It does not access GitHub,
run reviews or publish comments. DeepSeek is an external paid API; no GPU is required.

## Source and tests

- `n8n/workflow.json`: importable workflow, with the production route and canvas layout.
- `n8n/code/`: JavaScript embedded in visible n8n Code nodes and field expressions.
- `n8n/sql/`: queries embedded in PostgreSQL nodes, plus the database schema.
- `n8n/build_workflow.py`: offline export builder; preserves node IDs and layout.
- `embedding_service/`: inference API only.

```sh
uv sync --frozen
uv run pytest -q -m 'not integration'
node --test n8n/tests/workflow.test.cjs
uv run ruff check embedding_service tests
# For the PostgreSQL integration test:
docker compose -p diffmind-tests -f compose.test.yaml up -d
uv run pytest -q
```

The export contains credential references, never credential values. Imports must
map those references to the destination instance's credentials. See
[deployment instructions](deployment/README.md) and [validation evidence](deployment/VALIDATION.md).

## Reviews and commands

Opened, reopened, ready-for-review and synchronized PRs trigger reviews; drafts are
skipped. Commit updates use the last published head when it is still an ancestor.
Findings include inline diff comments, evidence links and optional single-line fixes.
Delivery/head deduplication and saved publication intents limit duplicate comments.

Reply in an **inline review discussion** with `/diffmind review`,
`/diffmind full-review`, `/diffmind pause` or `/diffmind resume`. Commands require
repository write permission. The GitHub App subscribes to `pull_request` and
`pull_request_review_comment`. Timeline commands require an additional
`issue_comment` subscription; that is not enabled in the current App setup.

Trusted rules come from `.diffmind.json` on the PR target branch:

```json
{"exclude": ["fixtures/*", "generated/*"], "instructions": "All money values are integer cents."}
```

## Limits

This version does not execute tests or analyzers, resolve GitHub threads automatically,
chat with reviewers, learn feedback, or open fix PRs. Chunking uses heuristics, not a
full AST parser. Selected secret patterns and filenames are filtered; this is not a
comprehensive secret scanner. Relevant code and PR text are sent to DeepSeek.

One review runs at a time. Source limits are 15 MB, 10,000 files, 250 KB per file and
30,000 chunks; model review is capped at 12 batches and five findings per run.
Dense inputs include at most 450 UTF-8 bytes of path, symbol and source, leaving
headroom below BGE's 500-token service guard. Long lines are split with source
offsets and line locations preserved; source text is never silently truncated.
Dense queries use the same byte bound; lexical queries retain their separate budget.
This conservative bound produces more chunks than character-only windows and may
increase initial indexing time. Changing the embedding model requires revalidating it.

The inference API accepts 128 inputs per request but computes at most 24 texts at a
time on CPU. Same-revision index reuse requires both a matching input fingerprint
and Qdrant's exact point count; a missing or incomplete index is rebuilt. A new
commit still writes a complete revision snapshot, while unchanged embedding inputs
reuse the service cache. Changed-files-only Qdrant updates are not implemented.

Measured on a roughly 9,200-chunk repository, the former 16-minute vector-packing
step fell to 2.3 seconds with native field mapping. A 128-input warm-cache rebuild
and review took 3m22s while an older review was also running; reusing that revision
completed in 40 seconds. First-time embeddings still depend on repository size and
CPU capacity. See the validation record for the workloads and limits of these timings.
Skipped content is reported as partial coverage. Embeddings run with a 1 GB memory
limit and Qdrant with 2 GB; large-repository peak usage and latency remain unmeasured.
Monitor Git caches, execution history, PostgreSQL history and model cache disk usage.

This repository also contains a synthetic refund ledger for testing. Deliberately
faulty fixtures belong in labelled test PRs, never in the default branch.
