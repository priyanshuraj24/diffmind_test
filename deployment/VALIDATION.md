# Native n8n validation

Synthetic evaluation: https://github.com/priyanshuraj24/diffmind_test/pull/3
Implementation: https://github.com/priyanshuraj24/diffmind_test/pull/2
Production workflow: https://n8n.weberaai.com/workflow/q4ifTzOOrmBYZlXE

## Completed live scenarios (October 28, 2026)

| Scenario | Execution | Observed result |
| --- | --- | --- |
| Ownership and cumulative-refund guards removed, head a742486 | 956, native test workflow | Two inline findings; 12 indexed chunks |
| Amount validation removed; 35 helper functions added, head 1f0aa38 | 987, native test workflow | Third defect found without duplicate findings; 48 chunks across two embedding batches |
| Restore all guards, head 8be8290 | 999, native test workflow | Zero new findings; summary recognized restored guards |
| Inline reply command delivered by the App after production cutover | Intake 1011, review 1012, original workflow | Complete native review succeeded with repository hook inactive |

The larger helper fixture initially crowded the changed ledger out of retrieval.
The validator rejected missing evidence. Per-file evidence reservation and balanced
query terms fixed this; the regression has a dedicated test. Retrieval is mandatory
and visible, with separate semantic, BM25 and exact-symbol Qdrant requests.

## Fresh route verification (October 29, 2026)

Reply https://github.com/priyanshuraj24/diffmind_test/pull/3#discussion_r4408993659
produced successful production webhook execution 1741. It ran signature verification,
App authentication, collaborator permission checking, normalization and durable queueing.
The original workflow is active with 72 nodes; both legacy wrappers and the temporary
native workflow are inactive. The repository-specific test webhook is inactive.

Follow-on review 1742 exposed a missing Qdrant container. After SSH access recovered,
the container was recreated from the saved compose file with its persistent storage;
both existing collections survived. Its restart policy is `unless-stopped` and it is
attached to the network shared with n8n. No old review worker container is running.

A harmless docstring commit `d00a48cb88f45ddd5c177fcf85c35803a0420544` then generated
a real GitHub `pull_request` commit-update webhook: intake **1751** and review **1752**
both succeeded on the original production workflow. Review 1752 completed in 11.1
seconds after claim, indexed 48 chunks, retrieved 4 exact-symbol, 30 lexical and 30
semantic candidates, completed both DeepSeek passes, and saved published state.
The PR summary was updated with zero findings and incremental review enabled.
The corrected sample passed its three tests from the test branch's own worktree.

The running inference service matches the committed source hash. Real two-item dense
and sparse requests passed in both document and query modes. Observed idle memory:
Qdrant 21.6 MiB and inference 292.8 MiB; these are not peak measurements.

## Local verification

October 29: six Python unit/sample tests and twelve Node workflow tests passed; Ruff
passed. Tests cover inference authentication, batching/cache, oversized token input,
diff positions, source exclusions, chunk ranges, per-file retrieval evidence, citation
validation and compilation of every exported Code node and expression.
The additional regression cases cover long Unicode lines, oversized path/symbol
metadata, exact source reconstruction, distinct fragments sharing a line, and the
separate dense-query bound.

## Embedding limit regression

A real 371-file repository exposed the character-only chunker's failure to account
for tokenizer expansion and the path/symbol prefix. The service correctly rejected
an oversized input with HTTP 422; disabling that guard would silently lose context.
The fixed n8n chunker bounds the complete input by UTF-8 bytes and fragments long
lines while preserving source locations and offsets. A replay of all source files
produced 3,747 chunks with exact source reconstruction. The running BGE tokenizer
measured a maximum of 204 tokens across those chunks, with none exceeding 500.
Private repository source used for this regression is not committed to this repository.
Production retry 1917 succeeded: all 3,747 chunks were indexed, 12 review batches
completed, five findings were saved and the review was published. Sixteen files
were reported as outside the review budget. Total execution time was about 9m54s,
including the first indexing pass; this is one workload, not a throughput guarantee.

## Git runner responsiveness

Three front-end PRs exposed a second issue: synchronous Git fetches blocked the code
runner's heartbeat, and n8n aborted affected runs after roughly 39 seconds. The Git
cache contained approximately 425 MiB of pack data. All Git operations now use
asynchronous child processes, including diff parsing and blob reads. Regression
tests verify that a timer continues running during a Git subprocess, blob input and
binary output are preserved, and failure diagnostics do not expose credentials.
Pinned fetches now retain per-PR head/base refs so subsequent fetches can negotiate
using the existing cache. A regression test checks those exact refspecs.

The real PostgreSQL queue test passed during the prior setup. It was not rerun on
October 29 because local Docker is stopped. Its connection now has a five-second
timeout. One upstream Starlette/httpx deprecation warning remains.

These fixtures establish small-repository behavior, not large-repository performance
or full CodeRabbit parity. Large-repository latency, peak memory, automatic thread
resolution and conversational review replies are not validated or implemented.
