---
id: FEAT-3498
type: FEAT
title: Policy builder host-approved run requests (queue/loop contracts)
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
blocks:
- FEAT-3504
relates_to:
- FEAT-3504
- ENH-3487
- ENH-3491
- ENH-3492
- BUG-3490
unproven_mechanism: true
spike_attempted: true
spike_completed: false
decision_needed: false
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 73
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 15
---

# FEAT-3498: Policy builder host-approved run requests (queue/loop contracts)

## Summary

Part A of the connected-execution feature extracted from FEAT-3488 (Part B, the same-origin page and serve routes, is FEAT-3504 and is blocked by this issue). Add host-side contracts to the queue and loop CLIs: a durable `awaiting_approval` request that no watcher or generic drain can run until the host explicitly accepts that one request; transactional request-key deduplication; builder-origin LOOP dispatch with the right cwd, no default timeout, and `--context issue_id=` binding; a structured start-metadata channel that returns the real loop instance identity; and plain Python functions that validate and persist an immutable lifecycle policy revision. Everything here is exercisable from Python and `ll-queue` with no browser and no `SseBridge` changes.

**Split rationale (2026-09-17):** the original five-step issue spanned nine source files, six docs, and eight test files; the queue/loop half carries all the concurrency risk and is independently testable, so it ships first as this issue. FEAT-3488 has landed (verified `d6785ffea`), so the former merge-ordering block is satisfied.

## Current Behavior

`queue_store.add_entry` creates immediately runnable pending rows; `ll-queue run` drains eligible entries and `--watch` consumes newly added work without per-entry approval. LOOP entries use `_run_loop_entry`, not `run_action`, and persist exit code/error/stdout/stderr rather than a structured loop instance ID. Queue rows have UUID identities with no request-key uniqueness. `_run_loop_entry` inherits the drainer's cwd and passes only the bare positional input; `_drain_once` claims, dispatches, and handles results inline in one loop body.

The prior isolated spike under `scripts/tests/spike/level2_run_handoff/` proved a prototype ledger, not these production queue contracts. In particular, forbidding the serve module from importing a runner does not prevent an already-running watcher from executing an inserted pending row.

## Expected Behavior

A caller (FEAT-3504's serve route, or a test) creates a run request bound to a project root, issue ID, and immutable revision hash; it lands as `awaiting_approval`. Watchers and generic drains never consume it. The host runs `ll-queue run --id <id> --approve` to accept exactly that request, or `ll-queue cancel` to reject it. When the loop starts, its real instance ID and run directory are recorded on the row and readable via `get_run_request` while running and after completion.

## Proposed Solution

### Scope and binding

- Every builder-origin request binds to a server-supplied `project_root`, never a caller-supplied browser path. Validate that the issue ID exists in that project at submission (`create_or_get_run_request`'s caller) and again at acceptance (`approve_and_claim_entry`). A server-derived `workspace_id` scopes the request key. Queue db anchoring and subprocess cwd must both use the same project root.
- First release accepts `issue_lifecycle` policies only; `validate_policy_revision` rejects other modes with a structured reason.
- No `SseBridge`, page, or renderer changes in this issue (FEAT-3504).

### Durable approval and execution

- Extend queue status with `awaiting_approval` for builder-origin requests. Generic `claim_entry`, one-shot drains, and `--watch` must never claim this status. Enforce it in the store transaction, not just UI filtering. Include migration/serialization/status-enumeration tests and preserve existing pending-entry behavior.
- Add an explicit per-entry host command `ll-queue run --id <queue UUID or 8+-char prefix> --approve`. It atomically accepts/claims only the selected awaiting request after rechecking bindings, issue existence, and persisted YAML hash; it does not drain unrelated entries and cannot combine with `--watch`. `--id` without `--approve` is a usage error in this release. Approval is recorded with `approved_at` and a binding snapshot as columns, not only inside result JSON. Normal queue execution remains compatible.
- `ll-queue cancel <id>` rejects awaiting requests without a run ID. Requeue/revive/retry paths must not bypass approval: an unapproved request (`approved_at` NULL) always returns to awaiting approval; an approved attempt (`approved_at` set) reuses existing retry/reclaim rules and returns to plain `pending`, where any generic drainer may retry it — approval is durable per request, not per attempt (see Program Design § Approval durability). Cancelling an active run is distinct from rejecting an awaiting request; do not promise that ordinary row cancellation kills a process.
- Nothing in the store or the submit helpers approves, drains, or launches a process. The authoritative test creates a request while a real queue watcher/drain loop is active and asserts zero dispatches before explicit approval.

### Request and revision identity

- Request payload (`RunRequest`): `{requestId, projectId, workspaceId, revisionId, yaml, issueId}`. `revisionId` is SHA-256 of the YAML's exact UTF-8 bytes; the server recomputes it and rejects mismatches. This is integrity binding, not detection of edits elsewhere. (The page-side snapshot/UUID lifecycle is FEAT-3504.)
- The request UUID is client-generated once per explicit submission; retries reuse it, Run again generates a new one. Terminal requests still deduplicate on the original UUID. A server unique key scoped to `workspace_id` maps request UUID to queue UUID; never pass a request UUID straight to `get_entry`.
- Provide a transactional create-or-get operation, with a unique constraint, rather than a lookup followed by `add_entry`. An existing key with differing bindings is a conflict. Concurrent submissions and retries after completion create exactly one row; a new request UUID creates another awaiting request. Return both request and queue IDs.
- `persist_policy_revision(yaml_bytes, revision_id, project_root) -> Path` writes the validated YAML atomically to `.loops/policy-builder/lifecycle-<revisionId[:12]>.yaml`, anchored to the project, using `write_bytes` on a temp file plus `os.replace` (not `write_text`, so no newline/encoding normalization can change the hash). The full hash lives on the queue row; the short filename keeps `_make_instance_id(loop_name)` (which uses the YAML stem) and run-dir names readable instead of 64-hex prefixed. Never overwrite an existing different payload; verify an existing file's full hash and raise a conflict on mismatch. At acceptance recheck immutable bytes/bindings before launch. Add `.loops/policy-builder/` to `.gitignore` alongside `.loops/.queue/` (revision artifacts are run inputs, not source).
- `validate_policy_revision(yaml_bytes, project_root) -> ValidationOutcome`: `load_and_validate(..., raise_on_error=False)` requires inspection of returned ERROR diagnostics, and can still raise YAML/shape/missing-field/file errors. Convert these expected failures to a structured outcome (errors and warnings distinguishable); use a temp validation file in the project artifact directory (there is no run directory before acceptance), preserving relative resolution behavior; clean temporary files; callers must not enqueue on errors. Validate lifecycle mode/required issue binding as well as generic FSM structure. Precedent for consuming the returned violations list: `cli/doctor.py:679`, `cli/logs.py:2349`.

### Run identity and observation

- Keep LOOP dispatch on `_run_loop_entry`. **Bind `issue_id` with `--context issue_id=<ID>`, not the positional input.** `cli/loop/run.py:176-186` only merges positional JSON keys that already exist in `fsm.context`; the generated lifecycle YAML declares `issue_id` as a `required: true` parameter with no default, which `seed_parameter_defaults` skips, so `{"issue_id": ...}` would land in `context.input` as a raw string and pre-run validation would fail with "Missing required context variable: 'issue_id'". `ll-loop run <name> --context issue_id=<ID>` is the documented lifecycle invocation (POLICY_ROUTER_GUIDE.md:356). Persist the revision file's absolute path as the action target and `issue_id` on the row; builder-origin dispatch appends `--context issue_id=<entry.issue_id>`.
- Run in the selected project cwd: `_run_loop_entry`'s `Popen` has no `cwd=` today, so pass `cwd=entry.project_root` (persisted at submission) for builder-origin entries. Enqueue with `ActionSpec.timeout=None`; the 120 s default would kill a real lifecycle run.
- `_run_loop_entry` currently receives only the `ActionSpec` (`_drain_once`, `cli/queue.py:591`). It must take the `QueueEntry` (for `id`, `project_root`, `issue_id`, and builder-origin detection via `request_id`), because approved entries retry through the generic drainer, so cwd/flag/metadata handling must live in the shared dispatch path, not only under `--id --approve`. Update its single call site.
- Add a machine-readable start-metadata channel from `cli/loop/run.py` to the queue LOOP runner, carrying the actual `instance_id` and run directory once initialization succeeds. A private metadata-output file passed to the child via a hidden flag (appended only for builder-origin entries) is sufficient; atomically publish it and validate its binding to the claimed entry. Because `_run_loop_entry` blocks in `communicate()`, the drainer needs a helper thread/poll to observe the file while the child runs (see Program Design § Start-metadata channel). Do not parse human stdout or invent a run ID from a queue UUID. The existing hidden `--instance-id` is not a general solution: normal foreground runs generate their own identity.
- Store and expose `loopInstanceId`/`runDir` when received, including while running; preserve them alongside exit/error/output fields at completion. Pre-launch failure/rejection leaves these null. Queue UUID, request UUID, and loop instance identity remain separate fields. Extend `cli/queue.py`, loop CLI argument registration/run initialization, and result persistence as required; these are code changes, not documentation-only touchpoints.
- `get_run_request(request_id, workspace_id)` is the readback primitive FEAT-3504's route will call; its return carries everything the wire `RunRequestStatus` needs.

## Integration Map

### Files to Modify

- `scripts/little_loops/queue_store.py`: approval status/transition, unique request mapping, transactional create-or-get, approval metadata, loop identity storage, `get_run_request`.
- `scripts/little_loops/cli/queue.py`: `_dispatch_claimed(entry)` factored from `_drain_once`; explicit single-entry accept/run; approval-safe cancellation/requeue/retry; `_run_loop_entry(entry)` with cwd, `--context issue_id=`, metadata flag, and metadata observation/result persistence.
- `scripts/little_loops/cli/loop/__init__.py`, `cli/loop/run.py`: private start-metadata output contract using actual initialized instance identity.
- New module `little_loops.cli.artifact.policy_revision` (does not exist yet): `validate_policy_revision`, `persist_policy_revision`, `RunRequest` dataclass — importable by FEAT-3504's serve route with no transport dependency.
- `.gitignore`: `.loops/policy-builder/`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/queue.py` — argparse registration site for `ll-queue run` flags at `main_queue()` lines 938,1042-1057; new `--id`/`--approve` flag wired here

_Moved to FEAT-3504:_ `policy_builder_core.mjs`, `policy-router-builder.html.tmpl`, `cli/artifact/policy_builder.py` renderer split, `cli/artifact/serve.py` flag and routes, `transport.py` POST dispatch.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_server/tools.py` — `_tool_queue_add` dispatch entry (lines 611,817,1151) and `queue_add` schema name; `_tool_loop_start` dispatch entry (lines 821,1265) and `loop_start` schema name — queue status updates and new approval semantics must be reflected in MCP tool behavior; do not advertise as approved-request execution equivalent per issue's scope
- `scripts/little_loops/mcp_server/tasks.py` — imports and calls `_make_instance_id` at line 104,107 — may need updates if the start-metadata channel changes the instance-id contract
- `scripts/little_loops/cli/queue.py` — `_STATUS_COLOR` dict at line 51 (used in `list`/`status`/`--watch` NDJSON coloring, lines 274,733,813) — must add `awaiting_approval` color entry once status added to `QUEUE_STATUSES`
- `scripts/little_loops/cli/doctor.py` — calls `load_and_validate` at line 679 (generic, unrelated to policy-revision validation, but confirms pre-parse exceptions flow)
- `scripts/little_loops/cli/logs.py` — calls `load_and_validate` at line 2349 (generic, unrelated to policy-revision validation)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_queue_store.py` — existing queue status/transition coverage; new tests: transition `awaiting_approval` → `pending` (approve phase), transactional create-or-get on request UUID, conflict detection on differing bindings, concurrent duplicate submissions. Tests likely to break: `TestStatusVocabulary::test_statuses_and_terminal_subset` (line 446,454-455) hardcodes `QUEUE_STATUSES` frozenset.
- `scripts/tests/test_cli_queue_run.py` — existing claim/drain/watch coverage; new tests: watcher-running concurrent submit produces `awaiting_approval` with zero dispatches, explicit `--id --approve` claims only the selected entry, generic drain never claims `awaiting_approval` entries, cancel/requeue/retry respect approval-safety. Tests likely to break: `TestStatusColorLock::test_status_color_keys_match_queue_statuses` (line 1126-1132) asserts `_STATUS_COLOR` keys == `QUEUE_STATUSES`. **Correction:** `TestCmdRunLoopDispatch::test_loop_entry_input_passed_as_positional` (line 384-395) and `test_loop_entry_intercepted_before_run_action` (line 340-357) were flagged here as breaking, but both use `_add_loop()` to build an ordinary (non-builder-origin) `ActionSpec` — per this issue's own Program Design § Start-metadata channel, the hidden flag is appended "only for builder-origin entries," so neither test's entry would receive it. `test_loop_entry_intercepted_before_run_action` also only asserts a `cmd[:3]` prefix, not full equality, so it would tolerate an appended flag regardless. Verified 2026-09-17: as currently written, neither test needs updating; this line's "likely to break" characterization contradicted the issue's own later design and has been corrected.
- `scripts/tests/test_feat_queue_mcp_tools.py` — covers MCP `queue_add`/`queue_list`/`queue_requeue` tools; new test for `awaiting_approval` guard in requeue predicate (mirroring the queue CLI tests)
- `scripts/tests/test_feat_3151_mcp_start_path.py` — exercises `loop_start` MCP tool; may need updates for new structured loop instance metadata contract
- `scripts/tests/test_cli_loop_background.py::TestMakeInstanceId` (line 1380-1427, drifted from a stale 1381-1425 citation) — tests `_make_instance_id()`, relevant to the new start-metadata channel contract
- New tests for `validate_policy_revision`/`persist_policy_revision`: `FileNotFoundError`/non-mapping/missing-field conversion, ERROR vs WARNING outcomes, unsupported mode, byte-exact persistence and hash parity with non-ASCII YAML, existing-file hash conflict, temp-file cleanup.
- A test that dispatches a builder-origin LOOP entry through a stubbed `ll-loop` child and asserts the argv contains `--context issue_id=<ID>` and the hidden metadata flag, `cwd` equals the persisted project root, and `timeout` is `None`; a sibling asserts an ordinary LOOP entry's argv and cwd are unchanged.

_Moved to FEAT-3504:_ `test_transport.py::TestLocalBridgeTransport` POST precedent, `test_enh3035_artifact_template_kit.py` / `test_policy_builder_emit.py` renderer-split coverage, `test_wiring_reference_docs.py` level-2 row.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `## little_loops.queue_store` code block (line 10997-11020) lists exported symbols; add new functions `create_or_get_run_request`, `approve_and_claim_entry`, `record_loop_started`, `get_run_request` with `(FEAT-3498)` citations. Inline comments for `QUEUE_STATUSES` and `QUEUE_TERMINAL_STATUSES` are at lines 11005-11006 (drifted from a stale 11001-11002 citation) and must reflect the new `awaiting_approval` status. Add a section for the new policy-revision module.
- `docs/reference/CLI.md` — `ll-queue run` reference section (line 912,4394-4395); add `--id` and `--approve` flag documentation and the approval/status semantics.
- `docs/guides/MCP_SERVER_GUIDE.md` (line 34,309,380,384,615) — reinforces "ll-queue out of scope for MCP" and documents `queue_add`/`loop_start` tool semantics; ensure new approval status doesn't risk re-advertising these as approved-request equivalents.
- `docs/ARCHITECTURE.md` — `## Queue DB (ll-queue)` section (line 834-844): add v4 schema-migration row (following the v3 ENH-3416 precedent, line 834-838) documenting new `loop_instance_id`, `run_dir` columns and request-id-to-queue-id mapping. Prose paragraphs (line 840-844) narrate existing transitions; expand for `awaiting_approval` → `running` (approve step) and corresponding claim/cancellation behavior.
- `docs/development/TESTING.md` — `FileNotFoundError` message example (line 295-298,333-336) for `load_and_validate` is pinned by existing test; the new policy-revision validation caller must catch and convert this exact exception type without changing its message.

_Moved to FEAT-3504:_ `API.md` `### SseBridge` prose, `CLI.md` `ll-artifact` subsections, `ARTIFACT_CONTROL_LEVELS.md` level-2 row and the POLICY_ROUTER_GUIDE.md cross-link, `ARCHITECTURE.md` `## Artifact Control Layer`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- (Transport/renderer findings moved to FEAT-3504.)
- Confirmed absent: no approval/eligibility concept exists in `queue_store.py` or `cli/queue.py` today (direct search for `approv` in both files, zero hits). The only existing "eligibility" concept is `_drain_once`'s `next_attempt_at`-based retry-backoff filter (`cli/queue.py:574`) and `claim_entry`'s matching `WHERE` clause (`queue_store.py:707-708`) — unrelated to human/host approval.

## API/Interface

Proposed operations (names finalized during implementation): `create_or_get_run_request`, `approve_and_claim_entry`, `record_loop_started`, `get_run_request`, `validate_policy_revision`, `persist_policy_revision`, `ll-queue run --id ID --approve`. All approval/claim/dedup invariants live in store transactions. Same-origin endpoints are FEAT-3504.

## Program Design

### Types

- `RunRequest {requestId, projectId, workspaceId, revisionId, yaml, issueId}` — input to `create_or_get_run_request`; FEAT-3504's POST route deserializes into it.
- `RunRequestStatus {requestId, queueId, status, bindings, loopInstanceId, runDir, result}` — shape `get_run_request`'s row maps to; FEAT-3504's GET route serializes it.
- `ValidationOutcome {ok: bool, errors: list[str], warnings: list[str], mode: str | None}` — return of `validate_policy_revision`.
- `LoopStartedMetadata {queueId, instanceId, runDir}` — contents of the child's private start-metadata file. `runDir` is absolute: `run_dir` derives from `loops_dir` relative to cwd, and `cmd_run` may `os.chdir` into a worktree (`cli/loop/run.py:~580`) before creating it, so resolve before writing.
- `status: Literal["awaiting_approval", "pending", "running", "done", "failed", "dead_letter", "cancelled"]` — `awaiting_approval` added to `QUEUE_STATUSES` (`scripts/little_loops/queue_store.py`); it is non-terminal and generic `claim_entry`/`--watch` never claim it.
- New nullable `QueueEntry` columns/fields (schema v4, plain `ALTER TABLE ADD COLUMN` like v2/v3): `request_id`, `workspace_id`, `project_root`, `revision_id`, `issue_id`, `approved_at`, `approval_snapshot` (JSON), `loop_instance_id`, `run_dir`. All null for ordinary entries. `to_dict`/`_from_row` gain matching camelCase keys. `loop_instance_id`/`run_dir` are populated only from the structured start-metadata channel, never parsed from stdout.
- Unique request key: v4 migration adds a partial unique index `ON queue_entries(workspace_id, request_id) WHERE request_id IS NOT NULL`. `request_id` is the client-generated UUID and is distinct from the store's `id` (queue UUID).

### Signatures

- `create_or_get_run_request(request: RunRequest, *, action: ActionSpec, project_root: Path, db_path=DEFAULT_DB_PATH, root: Path | None = None) -> tuple[QueueEntry, bool]` — transactional analog of `add_entry` (`queue_store.py:390`) keyed on `(workspace_id, request_id)`; inserts an `awaiting_approval` row or returns the existing one. The `bool` reports created vs fetched; a fetched row whose `revision_id`/`issue_id`/`workspace_id` differ raises a conflict error. Uses `BEGIN IMMEDIATE` like `claim_entry`, relying on the unique index (not a lookup-then-insert) so concurrent submits produce exactly one row.
- `approve_and_claim_entry(entry_id: str, *, expected_revision_id: str, expected_issue_id: str, owner_pid: int | None = None, db_path=DEFAULT_DB_PATH, root: Path | None = None) -> bool` — single-entry counterpart to `claim_entry` (`queue_store.py:669`); inside one `BEGIN IMMEDIATE` transaction rechecks bindings, stamps `approved_at`/`approval_snapshot`, and flips `awaiting_approval` → `running` (claimed) with the same `claimed_at`/`owner_pid`/`attempt` bookkeeping. Returns True iff this caller won the claim.
- `record_loop_started(entry_id: str, instance_id: str, run_dir: str, *, db_path=DEFAULT_DB_PATH, root: Path | None = None) -> bool` — persists the metadata-file readback; guarded `AND status = 'running'`.
- `get_run_request(request_id: str, workspace_id: str, *, db_path=DEFAULT_DB_PATH, root: Path | None = None) -> QueueEntry | None` — resolves the request key to the queue row; never pass a request UUID to `get_entry`.

- `validate_policy_revision(yaml_bytes: bytes, *, project_root: Path) -> ValidationOutcome` and `persist_policy_revision(yaml_bytes: bytes, revision_id: str, *, project_root: Path) -> Path` — pure functions in the new policy-revision module; no transport or queue imports.

All four store functions take `db_path`/`root` like `add_entry`/`revive_entry`, because a serve process (FEAT-3504) must anchor the db at `BRConfig.project_root` while `cli/queue.py` uses its module-level `QUEUE_DB_PATH` default. Builder-origin entries are enqueued at priority P3 with `ActionSpec.timeout=None` (the default of 120 s would kill any real lifecycle run).

### Approval durability and retry rules

Approval is durable per request, not per attempt:

- A row with `request_id` set and `approved_at` NULL is unapproved. `revive_entry` (which today has no status guard, `queue_store.py:634`) must return such a row to `awaiting_approval`, never `pending` (SQL `CASE WHEN request_id IS NOT NULL AND approved_at IS NULL THEN 'awaiting_approval' ELSE 'pending' END`). `ll-queue requeue` on a rejected (cancelled) builder request therefore re-awaits approval; the MCP `queue_requeue` tool shares `revive_entry`, so the rule covers it automatically. `reset_to_pending` needs no approval branch: it only transitions `running` rows, and a builder row can only reach `running` through `approve_and_claim_entry`, which stamps `approved_at` in the same transaction, so an unapproved `running` row cannot exist. Assert that invariant in a test rather than adding an untestable branch.
- A row with `approved_at` set is approved for its immutable bindings. After `--id --approve` runs it, a transient failure via `schedule_retry` and an owner death via `_reclaim_stale`/`reset_to_pending` both return it to plain `pending`, where any generic drainer (including a running `--watch`) may retry it without re-approval. This is intended and must be tested as such.
- `cancel_entry`'s SQL guard (`IN ('pending','running')`, `queue_store.py:625`) and `cmd_cancel`'s Python status list (`cli/queue.py:922`) both gain `awaiting_approval`. Rejection before acceptance leaves `loop_instance_id`/`run_dir` null.

### Host command and cwd

- `_drain_once` (`cli/queue.py:574-640`) claims, dispatches, and handles results inline in one loop body; there is no reusable per-entry function today. First factor the body after the claim into `_dispatch_claimed(entry, *, force_stop, db_path) -> dict` (dispatch, classify, `update_entry_result`/`schedule_retry`/`dead_letter_entry`/`cancel_entry`, and the processed record). `_drain_once` calls it; the new command calls it too.
- `ll-queue run --id <uuid-or-8+-char-prefix> --approve` resolves the id via `resolve_entry` (prefix support like every other subcommand), calls `approve_and_claim_entry`, dispatches that one entry through `_dispatch_claimed`, and exits. `--id` without `--approve` is rejected with a usage error in this release (single-entry execution of ordinary pending rows is out of scope). `--id` and `--watch` are mutually exclusive.
- `_run_loop_entry` (`cli/queue.py:382`) takes only the `ActionSpec`; change it to `_run_loop_entry(entry: QueueEntry)` (single call site, `cli/queue.py:591`) so it can read `id`, `project_root`, `issue_id`, and `request_id`. Builder-origin (`request_id` set) argv: `["ll-loop", "run", <abs revision path>, "--context", f"issue_id={entry.issue_id}", <hidden metadata flag>, <metadata path>]` with `cwd=entry.project_root`. Ordinary entries keep today's exact argv, no `cwd`. Because approved builder entries retry through the generic drainer, this branch lives here, not in the `--id --approve` command.
- `_run_loop_entry`'s `Popen` currently has no `cwd=`; the child inherits the drainer's cwd and `ll-loop run` derives `loops_dir` from config relative to it. `resolve_loop_path` (`fsm/loop_paths.py:40`) already accepts an absolute path, so the revision target works unchanged.

### Start-metadata channel

- The child receives the metadata path via a hidden `argparse.SUPPRESS` flag on `ll-loop run` (mirroring the existing hidden `--instance-id`), not an environment variable: env inherits into every descendant process and has caused phantom failures before. The flag is appended only for builder-origin entries, so ordinary LOOP entries keep today's exact argv and the two argv-equality tests in `test_cli_queue_run.py` stay valid.
- `_run_loop_entry` blocks in `proc.communicate(timeout)`, so nothing can observe the file mid-run. Run `communicate` on a helper thread (or poll `proc.poll()` with the pipes drained by threads) and have the main path poll the metadata file at a short interval; when it appears with a matching `queueId`, call `record_loop_started` so readback exposes identity while running. At completion, re-read the file once more before the existing result update so a race cannot lose it.
- The child writes the file atomically (temp + rename) immediately after `_pre_instance_id`/`run_dir` are fixed and the run dir exists (`cli/loop/run.py:199-208, 586`). A child that fails before that point never writes it.

### Immutable revision bytes

`cmd_policy_builder` writes with `write_text`; the revision file must be written with `write_bytes` (temp file + `os.replace`) so the on-disk SHA-256 equals the submitted hash byte-for-byte, with no newline or encoding normalization. Filename is `lifecycle-<revisionId[:12]>.yaml`; on collision with an existing file whose full-content hash differs, raise a conflict rather than overwrite.

### Call Path

Caller (test, or FEAT-3504's route) → `validate_policy_revision` wraps `load_and_validate` (`fsm/validation/structural_rules.py:1873`) with `raise_on_error=False` on a temp file → `persist_policy_revision` → `create_or_get_run_request` → row is `awaiting_approval`. Host `ll-queue run --id ID --approve` → `approve_and_claim_entry` → `_dispatch_claimed` → `_run_loop_entry(entry)` (`cli/queue.py:382`) with `cwd=project_root`, `--context issue_id=`, and the hidden metadata flag → child `cmd_run` initialization writes the metadata file → drainer poll → `record_loop_started` → existing result update. `get_run_request` → mapped row. Generic `claim_entry` never claims awaiting requests (its `status = 'pending'` guard already excludes them; the test still must prove it against a live watcher).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- `claim_entry` (`queue_store.py:669`) is currently the only queue-transition function using explicit `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK` transactional isolation (`isolation_level=None`, guarded `UPDATE ... WHERE status='pending'`, lines 702-716); every other terminal transition (`update_entry_result`, `schedule_retry`, `dead_letter_entry`, `cancel_entry`) uses a plain guarded `UPDATE` without explicit `BEGIN IMMEDIATE`. `create_or_get_run_request`/`approve_and_claim_entry` should mirror `claim_entry`'s pattern specifically, not the other transition functions'.
- The insertion point for a new `awaiting_approval` status value is `QUEUE_STATUSES = frozenset({"pending", "running", "done", "failed", "dead_letter", "cancelled"})` and `QUEUE_TERMINAL_STATUSES` (`queue_store.py:155-156`) — the module docstring states every other status enumeration site derives from or is locked against these two frozensets. Any new eligibility predicate in `claim_entry` must compose with, not replace, the existing `next_attempt_at` backoff gate already in its guarded `WHERE` clause (lines 704-709).
- `_run_loop_entry` (`cli/queue.py:382`) dispatches LOOP actions via `subprocess.Popen(["ll-loop", "run", action.target, ...], start_new_session=True)` (lines 411-417) — a fresh out-of-process child, not an in-process call. A start-metadata channel must therefore cross a real subprocess boundary (a file, as the issue already proposes), not a shared Python object.
- `cli/loop/run.py`'s hidden `--instance-id` flag exists at `cli/loop/__init__.py:231` (`argparse.SUPPRESS`) for the `run` subcommand. The `resume` subcommand also defines an `--instance-id` at line 501, but that one is **not** hidden — it carries a real user-facing `help=` string; the `argparse.SUPPRESS` at line 498 there belongs to a different flag (`--foreground-internal`), not to `resume`'s `--instance-id`. This doesn't change the issue's conclusion (the `run`-subcommand hidden flag is still a background-relaunch mechanism, not a general solution), but the "and again for `resume`" parenthetical overstated which flag is hidden. Normal foreground `cmd_run` resolves its own instance id via `_make_instance_id(loop_name)` (`cli/loop/runner.py:136`) at `cli/loop/run.py:199-203` when `args.foreground_internal` is unset — confirming a normal foreground run never receives an externally supplied id.
- `load_and_validate(..., raise_on_error=False)` (`fsm/validation/structural_rules.py:1873`, drifted from a stale `:1860` citation) still raises unconditionally on `FileNotFoundError` (line 1898), non-mapping YAML (line 1904), and missing required top-level fields (line 1924) — only post-parse structural/reachability validator output (`validate_fsm` plus four more passes — `_validate_with_bindings`, `_validate_loop_references`, `_validate_fragment_bindings`, `_validate_artifact_output_subloop_reachability` — lines 1964-1977, not "three more passes" at 1951-1957) is converted to a returned `(fsm, errors)` tuple instead of raising. **Correction:** the claim that "there is no existing precedent... for consuming that returned list" was inaccurate. `FSMExecutor._execute_sub_loop` (`executor.py:1116`) and `_validate_with_bindings` itself (`structural_rules.py:297`) do discard it (`child_fsm, _ = load_and_validate(...)`), but two call sites cited elsewhere in this same issue's own Integration Map — `cli/doctor.py:679` and `cli/logs.py:2349` — **do** consume the returned violations list (checking `any(v.severity == ERROR for v in violations)`). The new validation-response conversion has an established call-site pattern to follow after all.

## Implementation Steps

1. Implement/store-test approval eligibility, atomic request-key mapping, and `get_run_request`; update queue status consumers.
2. Factor `_dispatch_claimed` from `_drain_once`; add `ll-queue run --id ID --approve`; prove the production queue path with watcher-running, concurrent-submit, cancellation, retry/revive, and per-entry acceptance tests.
3. Change `_run_loop_entry` to take the entry; add cwd, `--context issue_id=`, `timeout=None`, the hidden metadata flag, and the metadata observation thread; add the child-side metadata write in `cli/loop/run.py`; test with a stubbed `ll-loop` child.
4. Add the policy-revision module (`validate_policy_revision`, `persist_policy_revision`, `RunRequest`) with byte-exact and non-ASCII hash tests; add `.loops/policy-builder/` to `.gitignore`.
5. Update docs. Port useful spike assertions to these production paths, then delete the old spike directory.

(Former steps 4–5, renderer split / serve routes / page UI, are FEAT-3504.)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `awaiting_approval` status to `QUEUE_STATUSES` frozenset (`QUEUE_TERMINAL_STATUSES` unchanged — it is non-terminal)
- Add `awaiting_approval` color entry to `_STATUS_COLOR` dict in `cli/queue.py:51`
- Bump `SCHEMA_VERSION` to 4 and append the v4 migration (new nullable columns + partial unique index on `(workspace_id, request_id)`) to `_MIGRATIONS` in `queue_store.py:116-150`; extend `QueueEntry` dataclass, `to_dict`, `_from_row` (`queue_store.py:334-383`)
- Add `awaiting_approval` to `cancel_entry`'s SQL guard (`queue_store.py:625`) and `cmd_cancel`'s status list (`cli/queue.py:922`); add the approval-aware target status to `revive_entry` (`queue_store.py:634`, currently unguarded) and `reset_to_pending` (`queue_store.py:491`)
- Factor `_dispatch_claimed(entry, ...)` out of `_drain_once`'s loop body (`cli/queue.py:574-640`) so `--id --approve` and the drain loop share one dispatch/result path
- Change `_run_loop_entry(action)` to `_run_loop_entry(entry)` and update its single call site (`cli/queue.py:591`); add `cwd=` to its `Popen` (`cli/queue.py:411`), the `--context issue_id=` argument, and the helper-thread/poll structure around `communicate()` for metadata observation
- Add `.loops/policy-builder/` to `.gitignore` (the `.loops/` block, lines 89-97)
- `ll-queue list`/`status` output shows request id, issue id, and revision id for builder-origin rows
- Update hardcoded status vocabulary in `_tool_queue_list` MCP tool description (`mcp_server/tools.py:920-925`) and test assertion in `test_queue_store.py:446,454-455` (TestStatusVocabulary)
- Update `test_status_color_keys_match_queue_statuses` locked test in `test_cli_queue_run.py:1126-1132` once `_STATUS_COLOR` entry is added
- Wire `--id` and `--approve` flags into argparse at `cli/queue.py:main_queue()` lines 938,1042-1057
- Add `_make_instance_id` reference in `mcp_server/tasks.py` if start-metadata contract changes (line 104,107)
- `test_loop_entry_input_passed_as_positional` and `test_loop_entry_intercepted_before_run_action` in `test_cli_queue_run.py` lines 384-395,340-357 exercise ordinary (non-builder-origin) entries and per Program Design § Start-metadata channel should NOT need updating once the LOOP subprocess metadata-file flag is added (see Tests section correction above) — verify this holds at implementation time rather than assuming breakage
- Port reusable assertions from `scripts/tests/spike/level2_run_handoff/test_level2_run_handoff.py`: `test_submit_creates_pending_record_not_auto_decided`, `test_duplicate_submit_returns_existing_record_without_retriggering`, `test_complete_rejects_binding_mismatch`, `test_submit_rejects_missing_binding_fields`, `test_ledger_persists_across_process_restart`, `test_observe_reflects_transitions_without_synchronous_decision_in_submit` into production test files (`test_queue_store.py`, `test_cli_queue_run.py`), then delete the spike directory
- Update `docs/reference/API.md` line 10997-11020 to add new function exports and line 11005-11006 inline comments for status changes
- Update `docs/reference/CLI.md` lines 912, 4394-4395 with `ll-queue run --id ID --approve`
- Update `docs/ARCHITECTURE.md` lines 834-844 to add v4 schema-migration row (following ENH-3416 v3 precedent) and expand prose for `awaiting_approval` transitions
- Ensure new policy-revision validation caller catches pre-parse exceptions from `load_and_validate` without changing message format (pinned by existing docs/development/TESTING.md example line 295-298)

## Acceptance Criteria

- [ ] Submitting while a watcher runs produces `awaiting_approval` and zero subprocess dispatches. Generic drain, direct generic claim, requeue/revive, and restart cannot bypass approval. Existing ordinary pending jobs still execute.
- [ ] Reviving or requeueing a rejected/unapproved builder request (via CLI or MCP `queue_requeue`) returns it to `awaiting_approval`, not `pending`. An approved entry that hits a retryable failure or owner death returns to `pending` and is retried by a generic drainer without re-approval.
- [ ] Builder-origin LOOP dispatch runs with `cwd` equal to the persisted project root, `--context issue_id=<ID>` in argv (not a positional JSON input), and no 120 s default timeout; ordinary LOOP entries keep today's exact argv and cwd behavior. The same branch runs on a generic-drainer retry of an approved entry.
- [ ] Explicit host acceptance claims only the selected request exactly once; cancellation before acceptance produces no run. Bindings and issue existence are rechecked; unrelated queue entries are untouched by the single-entry command. `_drain_once` behavior is unchanged after the `_dispatch_claimed` factoring (existing drain/watch tests pass).
- [ ] Concurrent duplicate submits and retries after terminal completion map to one queue UUID; conflicting payloads under one request ID fail. A new request UUID creates a fresh awaiting request.
- [ ] Invalid YAML syntax/shape, ERROR diagnostics, missing issue, wrong workspace, unsupported mode, revision mismatch, and changed on-disk artifact are rejected with structured diagnostics and no runnable entry.
- [ ] Persisted YAML is byte-identical to the input (SHA-256 parity including non-ASCII), immutable, project-anchored, and gitignored. Subprocess target/input/cwd match the accepted lifecycle revision and issue, with no real LLM or implementation runs in tests.
- [ ] A stub child startup publishes a real-format instance identity and an absolute run dir via the structured channel; readback exposes them while running and after completion, distinct from request/queue IDs. Startup failures and rejection leave them null. Stub the LOOP subprocess path, not `run_action`.
- [ ] No store, revision, or dispatch function approves or launches anything implicitly; the live-watcher test enforces the boundary.
- [ ] CLI approval/status semantics and the v4 schema are documented. Applicable local pytest gates pass.

## Use Case

A reviewed lifecycle policy for BUG-123 is submitted as a run request (by FEAT-3504's page, or by a test). Another queue watcher may already be running but cannot start it. The maintainer accepts that exact request with `ll-queue run --id <id> --approve` from the host session; the row records the real loop instance ID and run dir while it runs and the result on completion.

## Impact

- Priority: P3 — the host-side half of the authoring-to-execution gap; FEAT-3504 depends on it.
- Effort: Large — approval, queue concurrency, and child metadata integration.
- Risk: High until the production approval/watcher tests pass.
- Breaking change: Existing queue jobs remain compatible; queue schema/status consumers require migration coverage. `_run_loop_entry`'s signature changes (single internal call site).

## Scope Boundaries

Includes the `awaiting_approval` status, request-key dedup, explicit host approval, builder-origin LOOP dispatch (cwd, `--context issue_id=`, no timeout, metadata channel), immutable revision validation/persistence, and `get_run_request` readback. Excludes the same-origin page, serve routes, and `SseBridge` POST dispatch (FEAT-3504); autonomous page/serve execution; remote shell APIs; level-3 event interception; all-mode connected inputs; new retry/backoff policy; arbitrary YAML import; and the `_ResourceEntry` control-level forward slot. Offline suites belong to FEAT-3488.

## Spike History

Extracted from FEAT-3488: `scripts/tests/spike/level2_run_handoff/` and `.ll/spikes/spike-FEAT-3488.md` record the earlier isolated nine-test ledger prototype and isolation assertions. It was not promoted. That evidence does not retire the watcher approval, transactional dedup, or LOOP identity risks in this issue. Re-express the applicable assertions against production queue/serve code before removing the prototype; the new mechanism remains unproven until those tests pass.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Contract | docs/reference/ARTIFACT_CONTROL_LEVELS.md | Host approval and render-target ownership |
| Architecture | docs/ARCHITECTURE.md | Host runner and artifact integration |
| Reference | docs/reference/CLI.md | Queue and artifact serve commands |

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item).

Ran `/ll:verify-issues` against the current repo (2026-09-17). Decisions log: no active required rules, no violation. `ll-verify-evidence`: clean (0 findings). Dependency check: `blocked_by: FEAT-3488` — FEAT-3488 completed today with a matching `Blocks` backlink; satisfied, informational only, no DEP_ISSUES. No broken refs, missing backlinks, or cycles found among `blocked_by`/`relates_to` targets (all completed).

The overwhelming majority of this issue's file/line citations checked out exactly against current code (`SseBridge`/`LocalBridgeTransport` GET-only/POST-separate structure, `queue_store.py` schema/`claim_entry` transaction pattern, `_run_loop_entry`'s missing `cwd=`, `resolve_entry`'s prefix support, the v4-migration/partial-unique-index mechanism, and essentially all Integration Map line numbers). A handful of citations had drifted or were inaccurate; corrected in place:

- `cmd_policy_builder` is now at `policy_builder.py:62` (not 61), with five `.replace()` calls (not three) and a correspondingly shifted split point (pure-computation lines 73-115, CLI-tail lines 117-125). The split point itself is unaffected.
- The claim that `resume`'s `--instance-id` (`cli/loop/__init__.py:501`) is `argparse.SUPPRESS`-hidden was wrong — only the `run`-subcommand's `--instance-id` (line 231) is hidden; the `resume` one has a real `help=` string, and the `argparse.SUPPRESS` near line 498 belongs to `--foreground-internal`. Does not change the issue's conclusion about the hidden flag being a background-relaunch mechanism only.
- `load_and_validate` is at `structural_rules.py:1873` (not ~1860); its post-parse conversion covers four validator passes at lines 1964-1977 (not three at 1951-1957). More substantively, the claim "there is no existing precedent... for consuming that returned list" was wrong: `cli/doctor.py:679` and `cli/logs.py:2349` — both already cited elsewhere in this issue's own Integration Map — do consume it. The new validation-response conversion has an established pattern to follow.
- `test_policy_builder_emit.py` does not assert byte-identical golden HTML (its golden tests cover YAML fixtures); the actual byte-identity test lives in `test_enh3035_artifact_template_kit.py`, already cited separately.
- `TestMakeInstanceId` spans lines 1380-1427 (not 1381-1425).
- `docs/reference/API.md`: the `QUEUE_STATUSES`/`QUEUE_TERMINAL_STATUSES` inline-comment lines are 11005-11006 (not 11001-11002); no "GET-only" phrase exists at the cited 11478/11489 (those are a parameter description and a table separator) — the relevant prose is near line 11482.
- `docs/reference/CLI.md`: the cited 5062-5257 range is the whole `### ll-artifact` command family, not the policy-builder subsection alone (policy-builder is 5081-5102; serve is 5192-5257).
- The "**Binding now:**" cross-link requirement (lines 61-63) lives in `docs/reference/ARTIFACT_CONTROL_LEVELS.md`, not `docs/guides/POLICY_ROUTER_GUIDE.md` as originally cited in both the Documentation and Wiring Phase sections — fixed in both places.
- Self-contradiction resolved: the Tests/Wiring-Phase sections claimed `test_loop_entry_input_passed_as_positional` and `test_loop_entry_intercepted_before_run_action` would break once the metadata-file flag is added, but the Program Design section already states the flag is builder-origin-only. Verified against the actual tests (both use `_add_loop()`, an ordinary non-builder-origin entry; the second test only asserts a `cmd[:3]` prefix) — neither test needs updating. The "likely to break" language is corrected to reflect this.

Proposal-vs-code consequence check (B6): no defect found. The v4 schema-migration mechanism, the partial unique index, and `resolve_entry`'s prefix-matching signature are all mechanically consistent with what the proposal assumes.

## Status

**Open** | Created: 2026-09-17 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-09-18T02:40:10 - `41eda363-777e-4fc4-afbb-07ff19e7dfa2.jsonl`
- manual review - 2026-09-17 - split page/serve/transport half into FEAT-3504; fixed `issue_id` binding (positional JSON would not bind a required parameter — use `--context issue_id=`); pinned `_dispatch_claimed` factoring and `_run_loop_entry(entry)` signature; dropped vacuous `reset_to_pending` approval branch; absolute `runDir` in metadata; short revision filename; `.gitignore` entry
- `/ll:verify-issues` - 2026-09-18T01:26:23 - `eff5f7b6-7e2a-4e3b-9ab1-2c3de2810754.jsonl`
- manual review - 2026-09-17 - merged duplicate Program Design sections; pinned approval-durability/retry rules, v4 schema + partial unique index, `--id`/`--approve` semantics, LOOP cwd/timeout, metadata-channel thread/flag design, `write_bytes` persistence; clarified FEAT-3488 block as merge-ordering only
- `/ll:wire-issue` - 2026-09-17T06:29:23 - `cfe75f8a-6f82-4bce-bf08-9275049cd46d.jsonl`
- `/ll:reconcile-issue` - 2026-09-17T06:16:53 - `eb34f2f3-799f-4ff3-94f5-01cb135bc89a.jsonl`
- `/ll:refine-issue` - 2026-09-17T06:14:10 - `bdd11f79-301a-46b5-9233-83f283efd28d.jsonl`
- `/ll:format-issue` - 2026-09-17T06:04:13 - `673b8d7f-311f-49c5-91da-9f35cbc67a87.jsonl`
- `/ll:capture-issue` - 2026-09-17T06:00:15 - `673b8d7f-311f-49c5-91da-9f35cbc67a87.jsonl`
- manual review - 2026-09-17 - extracted FEAT-3488 Phase B with explicit queue approval, atomic request mapping, real LOOP identity, validation failures, project binding, and production-path verification
