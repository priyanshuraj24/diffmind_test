# Deployment and operations

The stack assumes an existing PostgreSQL server and an external Docker network
shared with n8n. It adds `diffmind-worker` and `diffmind-qdrant`; neither has a host
port. The optional Traefik labels expose only `/diffmind/`, never `/internal/`.

1. Create a dedicated PostgreSQL role/database owned by that role. Do not reuse
   n8n's database credentials. Back up the database and persistent data directory.
2. Copy `.env.example` to `.env`, restrict permissions to the service operator,
   and populate unique webhook/internal secrets, DeepSeek key, GitHub App ID,
   read-only private-key host path, repository allowlist and database URL.
3. Create `data/worker` owned by UID 1000 and `data/qdrant` with appropriate access.
   Keep the deployment directory private. Run `docker compose -p diffmind up -d --build`.
4. Create an n8n HTTP Header Auth credential named `DiffMind worker internal API`:
   header `Authorization`, value `Bearer <DIFFMIND_INTERNAL_TOKEN>`. Replace
   `SET_WORKER_CREDENTIAL_ID` in `n8n-coordinator.ts` with its ID.
5. Build/validate the two supplied SDK workflows with n8n's Workflow SDK tools.
   Publish ingress and coordinator. The coordinator polls once per minute and
   calls `/internal/run-once`. Keep `DIFFMIND_WORKER_ENABLED=false` in this mode.
   For standalone operation set it true and disable the n8n coordinator.
6. Install the GitHub App on the allowlisted repositories with Contents: read,
   Pull requests: read/write, Issues: read/write, and Metadata: read permissions.
   Create a repository webhook at `https://<n8n-host>/webhook/diffmind-v2`, JSON,
   events `pull_request` and `issue_comment`, using `DIFFMIND_WEBHOOK_SECRET`.
   The App installation is resolved from the repository if the event omits it.
7. Verify a ping, then a synthetic opened PR and synchronize event. Enable
   `DIFFMIND_PUBLISH=true` only for repositories intended to receive comments.

The ingress preserves the binary request body and GitHub signature. It responds
only after the worker validates HMAC-SHA256 and persists the event. n8n execution
data contains webhook metadata and review results; configure n8n execution pruning
and access control according to your organization's retention policy.

## Inspect

```sh
docker logs --tail 50 diffmind-worker
docker stats --no-stream diffmind-worker diffmind-qdrant
docker exec -i diffmind-worker python - <<'PY'
import json
from diffmind.config import Settings
from diffmind.store import Store
s = Settings()
db = Store(s.database_url.get_secret_value())
with db.connection() as c:
    rows = c.execute('SELECT id,repo,number,status,attempts,error FROM dm_jobs ORDER BY created_at DESC LIMIT 20').fetchall()
print(json.dumps(rows, default=str))
PY
```

Detailed traces in `dm_jobs.result` record the exact head, index coverage, selected
evidence, candidate counts for each channel, model token usage and rejected
findings. `/internal/jobs` provides the last twenty results with internal bearer
authentication. Never expose this endpoint or the database publicly.

Transient jobs retry up to three times with a one-minute delay. Publication
intents are persisted before GitHub writes; retries reconcile review/finding
markers belonging to the App. Manual commands enqueue new runs. Queued work for
older heads is superseded; in-flight work checks the current head before writes.
Comments remain bound to their reviewed commit if the head changes during the
network call. A later review handles the new head.

## Capacity and recovery

CPU embeddings use two threads and persist a content-addressed SQLite cache.
Qdrant dense vectors and payloads are on disk. A first index costs more than later
commits. Source budget defaults to 50 MB / 20,000 files / 100,000 chunks; files
over 250 KB and batch diffs over 40,000 characters are skipped visibly. Set budgets
lower for busier shared hosts. Track disk usage of both data directories and bare
Git repositories. Job history and caches currently require operator retention.

For upgrades, wait for the running job to finish, back up data, then rebuild the
worker. On interruption the job is reclaimable after its lease expires. Do not
run multiple deployments against the same Qdrant collection with different
embedding models; use a new collection when changing models or chunk schema.

Rollback: disable the repository webhook and the v2 coordinator, then stop the
worker. Keep PostgreSQL/Qdrant data and private settings. Re-enable the previous
workflow/webhook if it was cut over. Never run both reviewers against the same PR
unless duplicate comments are explicitly desired.
