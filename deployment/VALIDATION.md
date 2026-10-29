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

October 29: seven Python unit/sample tests and fourteen Node workflow tests passed; Ruff
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

All three affected open front-end PRs were retried and completed successfully:

| Execution | Indexed chunks | Review batches | New findings | Skipped review files | Duration |
| --- | ---: | ---: | ---: | ---: | --- |
| 2106 | 9,203 | 1 | 0 | 0 | 28m32s |
| 2138 | 9,206 | 2 | 0 | 0 | 18m04s |
| 2158 | 9,192 | 1 | 0 | 0 | 17m45s |

These are real workload observations. Full revision indexing remains costly even
with content-cached embeddings; the fixes establish correctness, not low review
latency. Historical failed executions remain in n8n for audit. Failed jobs belonging
to closed PRs were not retried. New commit deliveries continued queuing normally.

The real PostgreSQL queue test passed during the prior setup. It was not rerun on
October 29 because local Docker is stopped. Its connection now has a five-second
timeout. One upstream Starlette/httpx deprecation warning remains.

These fixtures do not establish full CodeRabbit parity. Automatic thread resolution
and conversational review replies are not implemented. The indexing measurements
below add one large-repository workload; they are not a general throughput guarantee.

## Indexing performance repair (October 29, 2026)

Profiling execution 2138 showed that 956.1 seconds of its 1083.8-second runtime were
spent in `Attach vectors to source chunks`, across 384 iterations. Dense document
embeddings took 36.3 seconds with 9,065 reused inputs and 141 new ones. The mapping
node was replaced with native Edit Fields, preserving vector-count validation and
visible source-to-vector mapping. No review worker was introduced.

The transport batch grew from 24 to 128 inputs; inference still uses 24-text CPU
batches in document and query modes. Regression tests cover the accepted 128-input
boundary, rejected 129-input requests, cache reuse, matching vector order, count
mismatches, and index manifests that cannot be accepted solely on a point count.

The inactive benchmark workflow uses a separate Qdrant collection, selects its job
read-only, and ends before any publication or queue mutation. It used the saved
9,206-chunk commit from the same large front-end repository. The PR merged during
testing; subsequent benchmark runs explicitly used its archived snapshot without
publishing. Production open/head/lease checks were not changed.

| Execution | Scenario | Duration | Observation |
| --- | --- | --- | --- |
| 2205 | Native field mapping, 32-input transport, warm embeddings | 4m15.6s | Mapping took 2.262s across 288 iterations; all 9,206 chunks indexed |
| 2218 | 128-input transport, warm embeddings, full snapshot rebuild | 3m22.0s | 72 embedding batches, all 9,206 dense and lexical inputs cached; two review batches completed |
| 2223 | Same revision reused | 40.0s | Exact count verified; zero document-embedding batches; both review batches completed |
| 2325 | Production `/diffmind full-review` on test PR 3 | 11.6s | 50 chunks, one embedding batch, summary published and job completed |
| 2558 | Production repeat command on the same test head | 10.4s | 50 chunks reused, zero document-embedding batches, summary updated |

An older production review was consuming resources during the large rebuild tests
and part of run 2223. It belonged to the now-merged PR and was canceled (execution
2198); its exact queue job was marked superseded so it would not retry. Execution
2215 ended at the closed-PR guard and is deliberately excluded from performance
claims. A stale test-job retry also ended correctly at the head guard (2322).

Production version `26b15f9f-1f9d-42f3-bc54-e33cba15beb1` is published on the original
workflow with 75 nodes and 10 groups. The temporary inference container was removed;
the original 1 GiB/two-CPU service now accepts the larger transport batch. Its real
dense/sparse document/query requests passed after deployment. The test PR retained
the same three bot inline findings and the same summary comment ID, confirming no
duplicate publication during the two new command tests.

The service cache avoids recomputing unchanged embeddings. New heads still write a
complete revision snapshot; file-level incremental Qdrant writes and larger
tokenizer-aware chunks are not part of this patch. First-time CPU embedding latency
remains. Full rebuild execution histories still retain vectors for inspection and
can be large; repeat-review index reuse avoids those vector histories.
