# Validation — 2026-10-28

Live synthetic PR: https://github.com/priyanshuraj24/diffmind_test/pull/1

| Scenario | Commit | Observed result |
| --- | --- | --- |
| Opened PR: authorization removed, prior refunds ignored | `e45519460039` | Two inline findings with evidence and suggested replacements |
| New commit: positive-amount validation removed | `19c41ad3d9ea` | One additional inline finding; incremental review; 12/13 embeddings reused |
| Manual full re-review | `19c41ad3d9ea` | Three known findings recognized; zero duplicate comments |
| Redeliver synchronize webhook | `19c41ad3d9ea` | No extra review job for the same delivery/head |
| Restore all guards and add a docstring | `401d13db0e9a` | Zero new findings; summary identified all three fixes |
| Manual review of fixed head | `401d13db0e9a` | Zero new findings; total inline comment count remained three |

All review runs above completed on the first attempt. First review retrieval
returned 9 exact, 13 lexical and 13 semantic candidates, including policy helpers
and tests outside the changed file. Subsequent reviews also recorded successful
results from all three channels. No optional model tool call controls retrieval.

The first four runs used 8,065 / 9,422 / 12,176 / 4,870 total model tokens
respectively (including verification when there were findings). Time from enqueue
to completion was 92 / 53 / 58 / 82 seconds, including queue scheduling and the
first embedding download. These figures are for a tiny five-file fixture and do
not establish large-repository throughput.

Observed memory after the first review: worker 320.4 MiB, Qdrant 32.15 MiB.
These are idle measurements, not peak measurements or capacity guarantees.

Local verification: 18 tests passed, covering real PostgreSQL and Qdrant, lexical
and semantic results, repository/revision isolation, changed index manifests,
embedding reuse, HMAC rejection, command permissions, leases, stale heads,
publication retry reconciliation and App JWT signing. Ruff and Git whitespace
checks passed. One upstream FastAPI TestClient/httpx deprecation warning remains.
The corrected sample application separately passed all three unittest cases.

Deployment scope: v2 runs only for the allowlisted test repository. The existing
App webhook and legacy production workflow remain unchanged. Expanding deployment
requires updating the explicit repository allowlist and webhook routing after
capacity and review-quality checks on representative repositories.
