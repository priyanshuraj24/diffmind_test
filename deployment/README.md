# Deploy and operate the n8n review flow

All review decisions run inside n8n. The supporting containers serve embeddings and
Qdrant only. An existing PostgreSQL server stores the durable review queue.

## Prerequisites and secrets

Use a trusted self-hosted n8n installation with Git available to Code nodes, the
`crypto`, `fs` and `child_process` built-in modules enabled, the `jsonwebtoken` external module available, and a writable persistent
`/home/node/.n8n-files` mount. The tested instance uses n8n 2.44.6. Git uses bare
repositories and argument arrays; repository hooks and repository code are never run.
Git subprocesses run asynchronously with a two-minute command timeout so long network
fetches do not block the runner heartbeat. Error messages classify failures without
printing Git stderr or credentials. Do not replace these calls with synchronous Git
commands in Code nodes: a long fetch can cause n8n to terminate an unresponsive runner.

Create a dedicated PostgreSQL role/database and apply `n8n/sql/schema.sql` there.
Do not reuse n8n's own database. Create these credentials in n8n and map the export:

| Reference | Type and value |
| --- | --- |
| diffmindNativePG | PostgreSQL connection to the review database |
| diffmindQdrantNative | HTTP Header Auth: `api-key`, private Qdrant API key |
| diffmindEmbeddingNative | HTTP Header Auth: `Authorization`, `Bearer <embedding token>` |
| mVyte7t4PdF9TQ8w | DeepSeek API credential |

Store these private files in n8n's persistent mount with operator-only access:

- `github.pem`: GitHub App private key.
- `diffmind-webhook-secret`: GitHub App webhook signing secret.
- `diffmind-native-config.json`: `{"app_id":1593885,"bot_login":"diffmind[bot]","allowed_repos":["owner/repository"]}`.

Start with an explicit allowlist. `allowed_repos: "*"` permits repositories accessible
to the App's installations. The current rollout uses this setting as authorized.

## Supporting services

Copy `.env.example` to a private `.env`; generate distinct embedding and Qdrant
secrets. Set the external Docker network shared with n8n. Create `data/worker`
writable by UID 1000 and persistent `data/qdrant` storage, then run:

```sh
docker compose -p diffmind -f compose.yaml up -d
docker compose -p diffmind-model -f compose.native.yaml up -d --build
```

On homescale the installed executable is `docker-compose`. No host ports are exposed.
n8n calls `http://diffmind-embeddings:8000` and `http://diffmind-qdrant:6333`.
The embedding container receives only its inference token. Its health endpoint checks
process availability; a real dense/sparse request is needed to verify loaded models.

Create Qdrant collection `diffmind_n8n_v3` with this PUT body at
`/collections/diffmind_n8n_v3`, using the private `api-key` header:

```json
{"vectors":{"dense":{"size":384,"distance":"Cosine","on_disk":true}},"sparse_vectors":{"bm25":{"modifier":"idf"}}}
```

Add keyword payload indexes for `repo`, `head` and `symbol` using PUT
`/collections/diffmind_n8n_v3/index` and `{"field_name":"repo","field_schema":"keyword"}`
(repeat for the other two fields). Back up PostgreSQL and Qdrant before upgrades.

## Workflow and GitHub routing

Import `n8n/workflow.json`, map credentials, set the workflow's error workflow to
itself so the Error Trigger records retries, and publish. Keep only one production
receiver and one active queue scheduler. The export is inactive to avoid accidental
activation on import. Rebuilding the export does not deploy it.

The existing App permissions are sufficient for the current rollout; no permissions
were expanded. Subscribe to `pull_request` and `pull_request_review_comment` events.
The production App webhook is:

`https://n8n.weberaai.com/webhook/3251bb49-11ef-4c93-8fec-681c0a73329d/webhook`

It now enters the rebuilt original workflow `q4ifTzOOrmBYZlXE` (75 nodes). The URL
was preserved; the old workflow contents were replaced. The test repository hook
704289110 is inactive so events are not delivered twice. Global commands are replies
in inline review discussions; timeline commands are not globally subscribed.

Disabled workflows: `C07dOoQFSOWfHWTX`, `mZSc0OsVXmYslZKI` (old forwarding wrappers),
and `xEChpD4m09cY8Pef` (isolated benchmark flow with no GitHub publication). The old `diffmind-worker` was stopped at
cutover and is not part of either current compose file.

## Indexing performance and upgrades

Deploy the embedding service supporting 128 inputs before publishing the workflow
that uses those transport batches. Its dense and sparse inference batches remain
24 texts, with two CPU threads and the existing 1 GiB container limit. The review
logic and vector mapping remain visible in n8n; no review worker is involved.

`Map vectors to source chunks` is a native Edit Fields node. Do not replace this
small mapping with a Code node inside the index loop: the previous repeated runner
handoff accounted for nearly 16 minutes on a 9,200-chunk warm-cache run. The mapping
still rejects mismatched dense/sparse vector counts before writing to Qdrant.

`Plan revision index reuse` fingerprints the chunk IDs, complete embedding inputs
and model/chunk-policy version. A small manifest lives beside the bare Git cache in
`diffmind-index-manifests/<head>.json`. `Require complete index` writes it atomically
only after Qdrant's exact count matches. Both the manifest and count must match to
skip indexing. Missing manifests, modified chunk inputs, partial indexes, and
retention-pruned revisions rebuild safely. Changing model or chunk semantics must
also update the fingerprint policy version and any incompatible collection schema.

The queue result includes `index.indexed`, `index.reused_revision` and
`index.embedding_batches` for inspection without loading large execution histories.
New heads still rebuild the revision snapshot using cached vectors for unchanged
inputs. Successful automatic executions are not saved, so empty one-minute queue
checks do not fill the execution list. Failed executions and manual debugging runs
are saved. Successful reviews still retain their result in the review database and
their summary on GitHub. Historical saved executions are unaffected; large saved
failure/manual histories can still be roughly 185 MB. Normal n8n retention should
bound storage.

## Operations and recovery

Inspect the webhook execution first, then the schedule execution claiming that job.
An idle schedule success does not establish that a review completed. Confirm the
Qdrant search nodes, both DeepSeek nodes, and `Save published head and findings` ran.
Failures retry up to three times with a delay; stale heads are superseded. Review
publication is guarded by a lease and current-head checks. A fresh permitted command
can request another review after an exhausted failure.

```sh
docker ps -a --filter name=diffmind
docker logs --tail 50 diffmind-embeddings
docker logs --tail 50 diffmind-qdrant
docker stats --no-stream diffmind-embeddings diffmind-qdrant
```

Use PostgreSQL to inspect `dmn_jobs` status, attempts and safe failure reason. Keep
n8n execution access restricted: execution data includes source snippets and ephemeral
GitHub installation tokens. Configure execution pruning and database/cache retention.
The vector index retains three revision heads per repository; Git bare repositories
and database history require operator retention. Inference cache is capped at 100,000
entries. No automated large-repository capacity guarantee has been established.

The prior original workflow is backed up privately on homescale at
`/home/hicoders/diffmind/old-workflow.json`; previous version
`6e47bb50-5a0d-4241-b07f-ae10a87fab93` is available in n8n history. The previous App
hook configuration is privately backed up under `data/worker/app-hook-before-native.json`.
Rollback requires restoring the matching workflow and signing secret together. Do
not activate old and new queue processors simultaneously.
