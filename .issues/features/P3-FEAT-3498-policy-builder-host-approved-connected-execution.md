---
id: FEAT-3498
type: FEAT
title: Policy builder host-approved connected execution
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T05:54:16Z'
parent: EPIC-3493
labels:
- policy-builder
epic: EPIC-3493
blocked_by:
- FEAT-3488
relates_to:
- ENH-3487
- ENH-3491
- ENH-3492
- BUG-3490
unproven_mechanism: true
spike_attempted: true
spike_completed: false
decision_needed: false
---

# FEAT-3498: Policy builder host-approved connected execution

## Summary

Extract former Phase B of FEAT-3488 into a separate connected-execution feature. Serve the policy builder locally, validate and persist an exact lifecycle policy revision, and submit a durable request that cannot run until the host explicitly accepts that request. Reuse the queue store with explicit approval eligibility, atomic request deduplication, and structured loop identity/result readback. Offline authoring and FEAT-3488 suites ship independently.

## Current Behavior

`ll-artifact serve` uses `SseBridge` with token/Host-checked GET routes only. `queue_store.add_entry` creates immediately runnable pending rows; `ll-queue run` drains eligible entries and `--watch` consumes newly added work without per-entry approval. LOOP entries use `_run_loop_entry`, not `run_action`, and persist exit code/error/stdout/stderr rather than a structured loop instance ID. Queue rows have UUID identities with no request-key uniqueness.

The prior isolated spike under `scripts/tests/spike/level2_run_handoff/` proved a prototype ledger, not these production queue contracts. In particular, forbidding the serve module from importing a runner does not prevent an already-running watcher from executing an inserted pending row.

## Expected Behavior

From a same-origin connected page, a user selects an issue in the server's project, reviews an immutable policy snapshot, and submits a request. The host sees the exact project/issue/revision and explicitly runs or rejects that one request. Watchers never consume unapproved requests. The browser observes approval, running/completion/failure/rejection and a real loop instance identifier when execution starts. Network failures preserve the draft and suite.

## Proposed Solution

### Scope and origin

- Add an opt-in flag on `ll-artifact serve`; no config flag is needed. Serve the builder at `GET /{token}/policy-builder` using a shared renderer factored from `cmd_policy_builder`, with the endpoint URL stamped in. The `file://` copy stays offline-only. Preserve Host/token checks for every method and route; no CORS headers.
- First connected release accepts `issue_lifecycle` policies only. Rubric requires a subject and other modes need different binding contracts; keep their offline exports available and explain why connected Run is unavailable.
- Bind repository identity and filesystem access to `BRConfig.project_root`, never a browser-supplied path. Add a project-scoped issue-list/read endpoint using existing issue discovery; validate an issue ID exists in that project again at submission and acceptance. `projectId` from ENH-3487 identifies the builder document, not the repository. Return a server-derived workspace identifier in the page/bootstrap and reject cross-workspace requests. Queue and subprocess cwd must use the same server project root.

### Durable approval and execution

- Extend queue status with `awaiting_approval` for builder-origin requests. Generic `claim_entry`, one-shot drains, and `--watch` must never claim this status. Enforce it in the store transaction, not just UI filtering. Include migration/serialization/status-enumeration tests and preserve existing pending-entry behavior.
- Add an explicit per-entry host command `ll-queue run --id <queue UUID> --approve`. It atomically accepts/claims only the selected awaiting request after rechecking bindings, issue existence, and persisted YAML hash; it does not drain unrelated entries and cannot combine with `--watch`. Approval is recorded with timestamp and binding snapshot. Normal queue execution remains compatible.
- `ll-queue cancel <id>` rejects awaiting requests without a run ID. Requeue/revive/retry paths must not bypass approval: an unapproved request always returns to awaiting approval; an approved attempt may reuse existing retry rules only with unchanged immutable bindings. Cancelling an active run is distinct from rejecting an awaiting request; do not promise that ordinary row cancellation kills a process.
- Serve routes only submit/read requests. They never approve, drain, launch a process, or use `LocalBridgeTransport`/level-3 interactions. An AST import guard is supplementary; the authoritative test submits while a real queue watcher/drain loop is active and asserts zero dispatches before explicit approval.

### Request and revision identity

- Request payload: `{requestId, projectId, workspaceId, revisionId, yaml, issueId}`. Freeze the YAML snapshot at submission; `revisionId` is SHA-256 of its exact UTF-8 bytes. Server recomputes it and rejects mismatches. This is integrity binding, not detection of edits elsewhere; later draft edits leave the queued revision unchanged and mark the UI as showing an older submitted snapshot. Disable submitting a changed preview until its snapshot is rebuilt.
- Generate a request UUID once per explicit submission and persist it with client submission state outside undoable authoring history. Retries, reconnects, and reloads reuse it. A deliberate Run again gets a new UUID after an explicit user action, even for identical project/revision/issue. Terminal requests still deduplicate on the original UUID. A server unique key scoped to its workspace maps request UUID to queue UUID; never pass request UUID straight to `get_entry`.
- Provide a transactional create-or-get operation, with a unique constraint, rather than a lookup followed by `add_entry`. An existing key with differing bindings is a conflict. Concurrent submissions and retries after completion create exactly one row; explicit Run again creates another awaiting request. Return both request and queue IDs.
- Persist validated YAML atomically to `.loops/policy-builder/<revisionId>.yaml`, anchored to the project. Never overwrite an existing different payload; verify an existing file's hash. At acceptance recheck immutable bytes/bindings before launch. Use a temp validation file in that project artifact directory (there is no run directory before acceptance), preserving relative resolution behavior.
- `load_and_validate(..., raise_on_error=False)` requires inspection of returned ERROR diagnostics, and can still raise YAML/shape/missing-field/file errors. Convert these expected failures to structured validation responses; clean temporary files; do not enqueue invalid YAML. Warnings remain distinguishable. Validate lifecycle mode/required issue binding as well as generic FSM structure.

### Run identity and observation

- Keep LOOP dispatch on `_run_loop_entry` and pass JSON `args.loop_input = {"issue_id": ...}` serialized as the positional input. Persist the content-addressed loop's absolute path as the action target. Run in the selected project cwd.
- Add a machine-readable start-metadata channel from `cli/loop/run.py` to the queue LOOP runner, carrying the actual `instance_id` and run directory once initialization succeeds. A private metadata-output file passed to the child is sufficient; atomically publish it and validate its binding to the claimed entry. Do not parse human stdout or invent a run ID from a queue UUID. The existing hidden `--instance-id` is not a general solution: normal foreground runs generate their own identity.
- Store and expose `loopInstanceId`/`runDir` when received, including while running; preserve them alongside exit/error/output fields at completion. Pre-launch failure/rejection leaves these null. Queue UUID, request UUID, and loop instance identity remain separate fields. Extend `cli/queue.py`, loop CLI argument registration/run initialization, and result persistence as required; these are code changes, not documentation-only touchpoints.
- Poll `GET /{token}/run-request/{requestId}` for `{requestId, queueId, status, bindings, loopInstanceId, runDir, result}` via the explicit mapping. Use method-aware dispatch plus bounded parameterized path matching in `SseBridge`; existing exact GET/history/SSE routes keep working.
- Browser hashing may be asynchronous with platform SHA-256; no sync-only API requirement or bespoke SHA-256 implementation is needed. Test UTF-8/hash parity with Python, including non-ASCII YAML. Keep authoring usable while hashing/request I/O is in flight.

## Integration Map

- `scripts/little_loops/templates/policy_builder_core.mjs`: build immutable lifecycle submission snapshots; do not run actions from scenario evaluation.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`: same-origin availability, issue selection, review/submission/status UI, durable request retry metadata outside undo history.
- `scripts/little_loops/cli/artifact/policy_builder.py`: reusable renderer for CLI file output and serve route.
- `scripts/little_loops/cli/artifact/serve.py`, `cli/artifact/__init__.py`: opt-in flag and project/issue/page/request routes.
- `scripts/little_loops/transport.py`: method-aware POST dispatch and parameterized request readback with existing Host/token protections.
- `scripts/little_loops/queue_store.py`: approval status/transition, unique request mapping, transactional create-or-get, approval metadata, loop identity storage.
- `scripts/little_loops/cli/queue.py`: explicit single-entry accept/run, approval-safe cancellation/requeue/retry, LOOP cwd and metadata observation/result persistence.
- `scripts/little_loops/cli/loop/__init__.py`, `cli/loop/run.py`: private start-metadata output contract using actual initialized instance identity.
- Queue status consumers, including `scripts/little_loops/mcp_server/tools.py`: status vocabulary/readback updates; do not advertise generic `queue_add`/`loop_start` as an equivalent approved-request execution path.
- Tests: queue store/CLI tests, transport/SSE bridge tests, policy-builder emit/golden tests, connected route integration tests under `scripts/tests/`, and `test_wiring_reference_docs.py`.
- Docs: `docs/reference/CLI.md`, `docs/guides/POLICY_ROUTER_GUIDE.md`, `docs/reference/ARTIFACT_CONTROL_LEVELS.md` (declare the connected builder render target at level 2; existing event page stays level 1).

## API/Interface

Proposed operations (names finalized during implementation): `create_or_get_run_request`, `approve_and_claim_entry`, `record_loop_started`, request lookup mapping, `ll-queue run --id ID --approve`, same-origin issue and run-request endpoints. All approval/claim/dedup invariants live in store transactions. The route's opt-in flag does not approve any request.

## Implementation Steps

1. Implement/store-test approval eligibility and atomic request-key mapping; update queue status consumers and explicit per-entry host acceptance.
2. Prove the production queue path with watcher-running, concurrent-submit, cancellation, retry/revive, and per-entry acceptance tests before connecting the page.
3. Add lifecycle validation, immutable artifact persistence, workspace/issue binding, and structured child start metadata; test LOOP subprocess behavior with stubs.
4. Factor the builder renderer; add same-origin page/issue/request routes and method dispatch without changing existing GET/SSE behavior.
5. Wire review/submission/retry/readback UI and update docs/golden output. Port useful spike assertions to these production paths, then delete the old spike directory.

## Acceptance Criteria

- [ ] Submitting while a watcher runs produces `awaiting_approval` and zero subprocess dispatches. Generic drain, direct generic claim, requeue/revive, and restart cannot bypass approval. Existing ordinary pending jobs still execute.
- [ ] Explicit host acceptance claims only the selected request exactly once; cancellation before acceptance produces no run. Bindings and issue existence are rechecked; unrelated queue entries are untouched by the single-entry command.
- [ ] Concurrent duplicate submits, reload/retry, and retries after terminal completion map to one queue UUID; conflicting payloads under one request ID fail. Explicit Run again creates a fresh awaiting request.
- [ ] Invalid YAML syntax/shape, ERROR diagnostics, missing issue, wrong workspace, unsupported mode, revision mismatch, and changed on-disk artifact are rejected with structured diagnostics and no runnable entry.
- [ ] UTF-8 hashes match Python; persisted YAML is immutable and project-anchored. Subprocess target/input/cwd match the accepted lifecycle revision and issue, with no real LLM or implementation runs in tests.
- [ ] A stub child startup publishes a real-format instance identity via the structured channel; readback exposes it while running and after completion, distinct from request/queue IDs. Startup failures and rejection leave it null. Stub the LOOP subprocess path, not `run_action`.
- [ ] Serve cannot approve/run; production behavioral tests enforce the level boundary. Existing Host/token checks cover new routes, existing GET/history/SSE tests pass, and no CORS headers are added.
- [ ] Offline/non-lifecycle pages show connected controls unavailable with a reason. Connection failure/reload retains authoring/scenarios and submission identity; edited drafts clearly distinguish current and submitted revisions.
- [ ] Connected builder is documented at level 2; CLI approval/status semantics and local-only verification instructions are documented. Golden and applicable local pytest/Node gates pass.

## Use Case

A maintainer runs offline scenarios, submits the reviewed lifecycle policy for BUG-123, then accepts that exact request from the host session. Another queue watcher may already be running but cannot start the request first. The browser displays the actual loop instance and result without losing the author's current draft.

## Impact

- Priority: P3 — closes the authoring-to-execution gap after offline foundations.
- Effort: Large — approval, queue concurrency, transport, and child metadata integration.
- Risk: High until the production approval/watcher tests pass.
- Breaking change: Existing queue jobs and offline generation remain compatible; queue schema/status consumers require migration coverage.

## Scope Boundaries

Includes opt-in lifecycle run requests, project-local issue selection, explicit host approval, immutable revision binding, dedup, and status/instance readback. Excludes autonomous page/serve execution, remote shell APIs, level-3 event interception, all-mode connected inputs, new retry/backoff policy, arbitrary YAML import, and the `_ResourceEntry` control-level forward slot. Offline suites belong to FEAT-3488.

## Spike History

Extracted from FEAT-3488: `scripts/tests/spike/level2_run_handoff/` and `.ll/spikes/spike-FEAT-3488.md` record the earlier isolated nine-test ledger prototype and isolation assertions. It was not promoted. That evidence does not retire the watcher approval, transactional dedup, or LOOP identity risks in this issue. Re-express the applicable assertions against production queue/serve code before removing the prototype; the new mechanism remains unproven until those tests pass.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Contract | docs/reference/ARTIFACT_CONTROL_LEVELS.md | Host approval and render-target ownership |
| Architecture | docs/ARCHITECTURE.md | Host runner and artifact integration |
| Reference | docs/reference/CLI.md | Queue and artifact serve commands |

## Status

**Open** | Created: 2026-09-17 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-09-17T06:00:15 - `673b8d7f-311f-49c5-91da-9f35cbc67a87.jsonl`
- manual review - 2026-09-17 - extracted FEAT-3488 Phase B with explicit queue approval, atomic request mapping, real LOOP identity, validation failures, project binding, and production-path verification
