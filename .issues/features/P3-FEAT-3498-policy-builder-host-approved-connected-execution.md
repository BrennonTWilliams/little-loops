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
reconcile_attempted: true
---

# FEAT-3498: Policy builder host-approved connected execution

## Summary

Extract former Phase B of FEAT-3488 into a separate connected-execution feature. Serve the policy builder locally, validate and persist an exact lifecycle policy revision, and submit a durable request that cannot run until the host explicitly accepts that request. Reuse the queue store with explicit approval eligibility, atomic request deduplication, and structured loop identity/result readback. Offline authoring and FEAT-3488 suites ship independently.

**Dependency note:** `blocked_by: FEAT-3488` is a merge-ordering block only — both issues edit `policy_builder_core.mjs` and `policy-router-builder.html.tmpl`, and this issue consumes ENH-3487's `projectId`. Implementation Steps 1–3 (queue approval/dedup, LOOP cwd/timeout/metadata channel, revision persistence) have no functional dependency on FEAT-3488 and may start before it lands; only Steps 4–5 (page/route wiring) must follow it.

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
- Add an explicit per-entry host command `ll-queue run --id <queue UUID or 8+-char prefix> --approve`. It atomically accepts/claims only the selected awaiting request after rechecking bindings, issue existence, and persisted YAML hash; it does not drain unrelated entries and cannot combine with `--watch`. `--id` without `--approve` is a usage error in this release. Approval is recorded with `approved_at` and a binding snapshot as columns, not only inside result JSON. Normal queue execution remains compatible.
- `ll-queue cancel <id>` rejects awaiting requests without a run ID. Requeue/revive/retry paths must not bypass approval: an unapproved request (`approved_at` NULL) always returns to awaiting approval; an approved attempt (`approved_at` set) reuses existing retry/reclaim rules and returns to plain `pending`, where any generic drainer may retry it — approval is durable per request, not per attempt (see Program Design § Approval durability). Cancelling an active run is distinct from rejecting an awaiting request; do not promise that ordinary row cancellation kills a process.
- Serve routes only submit/read requests. They never approve, drain, launch a process, or use `LocalBridgeTransport`/level-3 interactions. An AST import guard is supplementary; the authoritative test submits while a real queue watcher/drain loop is active and asserts zero dispatches before explicit approval.

### Request and revision identity

- Request payload: `{requestId, projectId, workspaceId, revisionId, yaml, issueId}`. Freeze the YAML snapshot at submission; `revisionId` is SHA-256 of its exact UTF-8 bytes. Server recomputes it and rejects mismatches. This is integrity binding, not detection of edits elsewhere; later draft edits leave the queued revision unchanged and mark the UI as showing an older submitted snapshot. Disable submitting a changed preview until its snapshot is rebuilt.
- Generate a request UUID once per explicit submission and persist it with client submission state outside undoable authoring history. Retries, reconnects, and reloads reuse it. A deliberate Run again gets a new UUID after an explicit user action, even for identical project/revision/issue. Terminal requests still deduplicate on the original UUID. A server unique key scoped to its workspace maps request UUID to queue UUID; never pass request UUID straight to `get_entry`.
- Provide a transactional create-or-get operation, with a unique constraint, rather than a lookup followed by `add_entry`. An existing key with differing bindings is a conflict. Concurrent submissions and retries after completion create exactly one row; explicit Run again creates another awaiting request. Return both request and queue IDs.
- Persist validated YAML atomically to `.loops/policy-builder/<revisionId>.yaml`, anchored to the project, using `write_bytes` on a temp file plus `os.replace` (not `write_text`, so no newline/encoding normalization can change the hash). Never overwrite an existing different payload; verify an existing file's hash. At acceptance recheck immutable bytes/bindings before launch. Use a temp validation file in that project artifact directory (there is no run directory before acceptance), preserving relative resolution behavior.
- `load_and_validate(..., raise_on_error=False)` requires inspection of returned ERROR diagnostics, and can still raise YAML/shape/missing-field/file errors. Convert these expected failures to structured validation responses; clean temporary files; do not enqueue invalid YAML. Warnings remain distinguishable. Validate lifecycle mode/required issue binding as well as generic FSM structure.

### Run identity and observation

- Keep LOOP dispatch on `_run_loop_entry` and pass JSON `args.loop_input = {"issue_id": ...}` serialized as the positional input. Persist the content-addressed loop's absolute path as the action target. Run in the selected project cwd: `_run_loop_entry`'s `Popen` has no `cwd=` today, so pass `cwd=entry.project_root` (persisted at submission) for builder-origin entries. Enqueue with `ActionSpec.timeout=None`; the 120 s default would kill a real lifecycle run.
- Add a machine-readable start-metadata channel from `cli/loop/run.py` to the queue LOOP runner, carrying the actual `instance_id` and run directory once initialization succeeds. A private metadata-output file passed to the child via a hidden flag (appended only for builder-origin entries) is sufficient; atomically publish it and validate its binding to the claimed entry. Because `_run_loop_entry` blocks in `communicate()`, the drainer needs a helper thread/poll to observe the file while the child runs (see Program Design § Start-metadata channel). Do not parse human stdout or invent a run ID from a queue UUID. The existing hidden `--instance-id` is not a general solution: normal foreground runs generate their own identity.
- Store and expose `loopInstanceId`/`runDir` when received, including while running; preserve them alongside exit/error/output fields at completion. Pre-launch failure/rejection leaves these null. Queue UUID, request UUID, and loop instance identity remain separate fields. Extend `cli/queue.py`, loop CLI argument registration/run initialization, and result persistence as required; these are code changes, not documentation-only touchpoints.
- Poll `GET /{token}/run-request/{requestId}` for `{requestId, queueId, status, bindings, loopInstanceId, runDir, result}` via the explicit mapping. Use method-aware dispatch plus bounded parameterized path matching in `SseBridge`; existing exact GET/history/SSE routes keep working.
- Browser hashing may be asynchronous with platform SHA-256; no sync-only API requirement or bespoke SHA-256 implementation is needed. Test UTF-8/hash parity with Python, including non-ASCII YAML. Keep authoring usable while hashing/request I/O is in flight.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy_builder_core.mjs`: build immutable lifecycle submission snapshots; do not run actions from scenario evaluation.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`: same-origin availability, issue selection, review/submission/status UI, durable request retry metadata outside undo history.
- `scripts/little_loops/cli/artifact/policy_builder.py`: reusable renderer for CLI file output and serve route.
- `scripts/little_loops/cli/artifact/serve.py`, `cli/artifact/__init__.py`: opt-in flag and project/issue/page/request routes.
- `scripts/little_loops/transport.py`: method-aware POST dispatch and parameterized request readback with existing Host/token protections.
- `scripts/little_loops/queue_store.py`: approval status/transition, unique request mapping, transactional create-or-get, approval metadata, loop identity storage.
- `scripts/little_loops/cli/queue.py`: explicit single-entry accept/run, approval-safe cancellation/requeue/retry, LOOP cwd and metadata observation/result persistence.
- `scripts/little_loops/cli/loop/__init__.py`, `cli/loop/run.py`: private start-metadata output contract using actual initialized instance identity.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/queue.py` — argparse registration site for `ll-queue run` flags at `main_queue()` lines 938,1042-1057; new `--id`/`--approve` flag wired here
- `scripts/little_loops/cli/artifact/serve.py` — opt-in flag registration at `add_serve_parser()` line 37

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
- `scripts/tests/test_transport.py::TestLocalBridgeTransport` (line 1052-1295) — POST dispatch precedent using `_lb_http_request` helper, model for new `SseBridge.do_POST` tests
- `scripts/tests/test_enh3035_artifact_template_kit.py` (line 19,65) — calls `cmd_policy_builder` directly; will need updates once renderer is factored into reusable + CLI-wrapper split
- `scripts/tests/test_policy_builder_emit.py` — calls `cmd_policy_builder` directly. **Correction:** its "golden" tests (`test_golden_yaml_validates`, etc.) validate golden *YAML* fixtures, not HTML byte-identity. The byte-identical golden-HTML assertion (`test_policy_builder_renders_byte_identically_to_golden_fixture`) actually lives in `test_enh3035_artifact_template_kit.py` (already cited separately below at lines 19,65) — that is the file that must preserve renderer-split identity or fail. Tests likely to break: any in `test_enh3035_artifact_template_kit.py` that assert literal output HTML structure if the split changes internal rendering.
- `scripts/tests/test_wiring_reference_docs.py` — parametrized `DOC_STRINGS_PRESENT` table (line 215-224); new row needed once level-2 render target is declared in `ARTIFACT_CONTROL_LEVELS.md`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `## little_loops.queue_store` code block (line 10997-11020) lists exported symbols; add new functions `create_or_get_run_request`, `approve_and_claim_entry`, `record_loop_started`, `get_run_request` with `(FEAT-3498)` citations. Inline comments for `QUEUE_STATUSES` and `QUEUE_TERMINAL_STATUSES` are actually at lines 11005-11006 (drifted from a stale 11001-11002 citation) and must reflect new `awaiting_approval` status. `### SseBridge` section (heading at line 11448, drifted from a stale ~11444 citation) documents the route set; **correction:** no literal "GET-only" phrase exists at lines 11478/11489 (11478 is the `config` parameter description, 11489 is a table separator) — the relevant existing text is around line 11482 ("Extra `GET` routes..."). Update that prose for method-aware POST dispatch and parameterized path matching while preserving the Host/token security contract.
- `docs/reference/CLI.md` — `ll-artifact policy-builder` reference subsection (actually lines 5081-5102, not the full 5062-5257 range cited, which spans the whole `### ll-artifact` command family including design-md export, render, dashboard); `ll-artifact serve` reference subsection (lines 5192-5257); `ll-queue run` reference section (line 912,4394-4395); add `--id` and `--approve` flag documentation.
- **Correction:** the "**Binding now:**" cross-link requirement at lines 61-63 lives in `docs/reference/ARTIFACT_CONTROL_LEVELS.md`, not `docs/guides/POLICY_ROUTER_GUIDE.md` (that phrase does not appear anywhere in POLICY_ROUTER_GUIDE.md). Cross-link connected-builder's level-2 declaration from `ARTIFACT_CONTROL_LEVELS.md:61-63` into `docs/guides/POLICY_ROUTER_GUIDE.md` per that requirement.
- `docs/guides/MCP_SERVER_GUIDE.md` (line 34,309,380,384,615) — reinforces "ll-queue out of scope for MCP" and documents `queue_add`/`loop_start` tool semantics; ensure new approval status doesn't risk re-advertising these as approved-request equivalents.
- `docs/ARCHITECTURE.md` — `## Queue DB (ll-queue)` section (line 834-844): add v4 schema-migration row (following the v3 ENH-3416 precedent, line 834-838) documenting new `loop_instance_id`, `run_dir` columns and request-id-to-queue-id mapping. Prose paragraphs (line 840-844) narrate existing transitions; expand for `awaiting_approval` → `pending` (approve step) and corresponding claim/cancellation behavior. `## Artifact Control Layer` section (line 920-936) references `LocalBridgeTransport`; may need expansion if the new serve routes warrant mentioning alongside `_drain_inbound()`.
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md` — add level-2 row to the `## Declared levels by render target` table (line 49-59) for connected policy-builder: `| \`ll-artifact serve\`'s policy-builder route (FEAT-3498; connected same-origin authoring + submission with host approval, project-scoped issue binding, immutable revision persistence) | 2 (project-local) |`. Ensure this row matches the existing two-column table style with parenthetical FEAT-id + mechanism clause.
- `docs/development/TESTING.md` — `FileNotFoundError` message example (line 295-298,333-336) for `load_and_validate` is pinned by existing test; the new policy-revision validation caller must catch and convert this exact exception type without changing its message.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- `transport.py`'s `SseBridge` route table (`_routes: dict[str, Callable[[handler], None]]`, built in `__init__` at `transport.py:1259`) is consulted only from `do_GET` (`_make_sse_bridge_handler`, `transport.py:1200-1246`) via an exact-string match on the post-token path remainder (`bridge._routes.get(route)`); there is no `do_POST` anywhere on this handler today, and no segment/parameter matching primitive to extend. The Host-header check and prefix-strip sequence that a new `do_POST` would need to replicate is inline inside `do_GET`, not factored into a shared helper (`_expected_hosts()` at `transport.py:476` is the only piece already factored out).
- `LocalBridgeTransport`'s `_make_local_bridge_handler` (`transport.py:624`) is a structurally separate, hand-hardcoded `do_GET`/`do_POST` implementation (its own `/interaction` route via if/elif) that does not share `SseBridge`'s `_routes` dict — it is not itself reusable as a parameterized-dispatch template.
- `cmd_policy_builder` (`cli/artifact/policy_builder.py:62`, drifted from a stale `:61` citation) has a clean split point: everything from `BRConfig` construction through the `html.replace(...)` injection calls — now five, not three (grammar, skill catalog, generator version, confidence gate, builder core JS; lines 73-115) — is pure computation producing an in-memory `html` string with no dependency on `args` beyond `active_theme`/config; only the final block — resolving `output_dir` from `args.output` and the `write_text`/`logger.success` calls (lines 117-125) — is CLI-file-output-specific. The split point itself still holds; only the line ranges and replace-call count had drifted (verified 2026-09-17).
- An existing renderer/CLI-wrapper split precedent already exists in this codebase: `cmd_serve`'s `_make_page_html_factory` (`cli/artifact/serve.py:138`) builds HTML from config and hands back a string, later consumed by `bridge.set_page_html(...)` rather than written to a file — the same shape `cmd_policy_builder` would need for a serve route.
- Confirmed absent: no approval/eligibility concept exists in `queue_store.py` or `cli/queue.py` today (direct search for `approv` in both files, zero hits). The only existing "eligibility" concept is `_drain_once`'s `next_attempt_at`-based retry-backoff filter (`cli/queue.py:574`) and `claim_entry`'s matching `WHERE` clause (`queue_store.py:707-708`) — unrelated to human/host approval.

## API/Interface

Proposed operations (names finalized during implementation): `create_or_get_run_request`, `approve_and_claim_entry`, `record_loop_started`, request lookup mapping, `ll-queue run --id ID --approve`, same-origin issue and run-request endpoints. All approval/claim/dedup invariants live in store transactions. The route's opt-in flag does not approve any request.

## Program Design

### Types

- `RunRequest {requestId, projectId, workspaceId, revisionId, yaml, issueId}` — wire payload of the POST submit route.
- `RunRequestStatus {requestId, queueId, status, bindings, loopInstanceId, runDir, result}` — wire payload of the GET readback route.
- `LoopStartedMetadata {queueId, instanceId, runDir}` — contents of the child's private start-metadata file.
- `status: Literal["awaiting_approval", "pending", "running", "done", "failed", "dead_letter", "cancelled"]` — `awaiting_approval` added to `QUEUE_STATUSES` (`scripts/little_loops/queue_store.py`); it is non-terminal and generic `claim_entry`/`--watch` never claim it.
- New nullable `QueueEntry` columns/fields (schema v4, plain `ALTER TABLE ADD COLUMN` like v2/v3): `request_id`, `workspace_id`, `project_root`, `revision_id`, `issue_id`, `approved_at`, `approval_snapshot` (JSON), `loop_instance_id`, `run_dir`. All null for ordinary entries. `to_dict`/`_from_row` gain matching camelCase keys. `loop_instance_id`/`run_dir` are populated only from the structured start-metadata channel, never parsed from stdout.
- Unique request key: v4 migration adds a partial unique index `ON queue_entries(workspace_id, request_id) WHERE request_id IS NOT NULL`. `request_id` is the client-generated UUID and is distinct from the store's `id` (queue UUID).

### Signatures

- `create_or_get_run_request(request: RunRequest, *, action: ActionSpec, project_root: Path, db_path=DEFAULT_DB_PATH, root: Path | None = None) -> tuple[QueueEntry, bool]` — transactional analog of `add_entry` (`queue_store.py:390`) keyed on `(workspace_id, request_id)`; inserts an `awaiting_approval` row or returns the existing one. The `bool` reports created vs fetched; a fetched row whose `revision_id`/`issue_id`/`workspace_id` differ raises a conflict error. Uses `BEGIN IMMEDIATE` like `claim_entry`, relying on the unique index (not a lookup-then-insert) so concurrent submits produce exactly one row.
- `approve_and_claim_entry(entry_id: str, *, expected_revision_id: str, expected_issue_id: str, owner_pid: int | None = None, db_path=DEFAULT_DB_PATH, root: Path | None = None) -> bool` — single-entry counterpart to `claim_entry` (`queue_store.py:669`); inside one `BEGIN IMMEDIATE` transaction rechecks bindings, stamps `approved_at`/`approval_snapshot`, and flips `awaiting_approval` → `running` (claimed) with the same `claimed_at`/`owner_pid`/`attempt` bookkeeping. Returns True iff this caller won the claim.
- `record_loop_started(entry_id: str, instance_id: str, run_dir: str, *, db_path=DEFAULT_DB_PATH, root: Path | None = None) -> bool` — persists the metadata-file readback; guarded `AND status = 'running'`.
- `get_run_request(request_id: str, workspace_id: str, *, db_path=DEFAULT_DB_PATH, root: Path | None = None) -> QueueEntry | None` — resolves the request key to the queue row; never pass a request UUID to `get_entry`.

All four take `db_path`/`root` like `add_entry`/`revive_entry`, because the serve process must anchor the db at `BRConfig.project_root` while `cli/queue.py` uses its module-level `QUEUE_DB_PATH` default. Builder-origin entries are enqueued at priority P3 with `ActionSpec.timeout=None` (the default of 120 s would kill any real lifecycle run).

### Approval durability and retry rules

Approval is durable per request, not per attempt:

- A row with `request_id` set and `approved_at` NULL is unapproved. `revive_entry` (which today has no status guard, `queue_store.py:634`) and `reset_to_pending` must return such a row to `awaiting_approval`, never `pending`. `ll-queue requeue` on a rejected (cancelled) builder request therefore re-awaits approval; the MCP `queue_requeue` tool shares `revive_entry`, so the rule covers it automatically.
- A row with `approved_at` set is approved for its immutable bindings. After `--id --approve` runs it, a transient failure via `schedule_retry` and an owner death via `_reclaim_stale`/`reset_to_pending` both return it to plain `pending`, where any generic drainer (including a running `--watch`) may retry it without re-approval. This is intended and must be tested as such.
- `cancel_entry`'s SQL guard (`IN ('pending','running')`, `queue_store.py:625`) and `cmd_cancel`'s Python status list (`cli/queue.py:922`) both gain `awaiting_approval`. Rejection before acceptance leaves `loop_instance_id`/`run_dir` null.

### Host command and cwd

- `ll-queue run --id <uuid-or-8+-char-prefix> --approve` resolves the id via `resolve_entry` (prefix support like every other subcommand), calls `approve_and_claim_entry`, dispatches that one entry through the existing `_drain_once` result-handling path, and exits. `--id` without `--approve` is rejected with a usage error in this release (single-entry execution of ordinary pending rows is out of scope). `--id` and `--watch` are mutually exclusive.
- `_run_loop_entry` (`cli/queue.py:382`) currently has no `cwd=` on its `Popen`; the child inherits the drainer's cwd and `ll-loop run` derives `loops_dir` from config relative to it. Builder-origin entries pass `cwd=entry.project_root` (persisted at submission) so dispatch does not depend on where the drainer was started. `resolve_loop_path` (`fsm/loop_paths.py:40`) already accepts an absolute path, so the content-addressed target works unchanged.

### Start-metadata channel

- The child receives the metadata path via a hidden `argparse.SUPPRESS` flag on `ll-loop run` (mirroring the existing hidden `--instance-id`), not an environment variable: env inherits into every descendant process and has caused phantom failures before. The flag is appended only for builder-origin entries, so ordinary LOOP entries keep today's exact argv and the two argv-equality tests in `test_cli_queue_run.py` stay valid.
- `_run_loop_entry` blocks in `proc.communicate(timeout)`, so nothing can observe the file mid-run. Run `communicate` on a helper thread (or poll `proc.poll()` with the pipes drained by threads) and have the main path poll the metadata file at a short interval; when it appears with a matching `queueId`, call `record_loop_started` so readback exposes identity while running. At completion, re-read the file once more before the existing result update so a race cannot lose it.
- The child writes the file atomically (temp + rename) immediately after `_pre_instance_id`/`run_dir` are fixed and the run dir exists (`cli/loop/run.py:199-208, 586`). A child that fails before that point never writes it.

### Immutable revision bytes

`cmd_policy_builder` writes with `write_text`; the revision file must be written with `write_bytes` (temp file + `os.replace`) so the on-disk SHA-256 equals the submitted hash byte-for-byte, with no newline or encoding normalization.

### Call Path

`ll-artifact serve` route handler → `cmd_policy_builder` (`cli/artifact/policy_builder.py:62`) renderer, reused for the same-origin page → `SseBridge` (`transport.py:1248`) method-aware dispatch adds the POST submit/GET run-request routes alongside existing GET/SSE routes → submit validates through `load_and_validate` (`fsm/validation/structural_rules.py:1873`) with `raise_on_error=False` on a temp file, persists the revision, then calls `create_or_get_run_request` → row is `awaiting_approval`. Host `ll-queue run --id ID --approve` → `approve_and_claim_entry` → `_run_loop_entry` (`cli/queue.py:382`) with `cwd=project_root` and the hidden metadata flag → child `cmd_run`/`PersistentExecutor` initialization writes the metadata file → drainer poll → `record_loop_started` → existing result update. Page GET → `get_run_request` → mapped row. Generic `claim_entry` never claims awaiting requests (its `status = 'pending'` guard already excludes them; the test still must prove it against a live watcher).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- `claim_entry` (`queue_store.py:669`) is currently the only queue-transition function using explicit `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK` transactional isolation (`isolation_level=None`, guarded `UPDATE ... WHERE status='pending'`, lines 702-716); every other terminal transition (`update_entry_result`, `schedule_retry`, `dead_letter_entry`, `cancel_entry`) uses a plain guarded `UPDATE` without explicit `BEGIN IMMEDIATE`. `create_or_get_run_request`/`approve_and_claim_entry` should mirror `claim_entry`'s pattern specifically, not the other transition functions'.
- The insertion point for a new `awaiting_approval` status value is `QUEUE_STATUSES = frozenset({"pending", "running", "done", "failed", "dead_letter", "cancelled"})` and `QUEUE_TERMINAL_STATUSES` (`queue_store.py:155-156`) — the module docstring states every other status enumeration site derives from or is locked against these two frozensets. Any new eligibility predicate in `claim_entry` must compose with, not replace, the existing `next_attempt_at` backoff gate already in its guarded `WHERE` clause (lines 704-709).
- `_run_loop_entry` (`cli/queue.py:382`) dispatches LOOP actions via `subprocess.Popen(["ll-loop", "run", action.target, ...], start_new_session=True)` (lines 411-417) — a fresh out-of-process child, not an in-process call. A start-metadata channel must therefore cross a real subprocess boundary (a file, as the issue already proposes), not a shared Python object.
- `cli/loop/run.py`'s hidden `--instance-id` flag exists at `cli/loop/__init__.py:231` (`argparse.SUPPRESS`) for the `run` subcommand. The `resume` subcommand also defines an `--instance-id` at line 501, but that one is **not** hidden — it carries a real user-facing `help=` string; the `argparse.SUPPRESS` at line 498 there belongs to a different flag (`--foreground-internal`), not to `resume`'s `--instance-id`. This doesn't change the issue's conclusion (the `run`-subcommand hidden flag is still a background-relaunch mechanism, not a general solution), but the "and again for `resume`" parenthetical overstated which flag is hidden. Normal foreground `cmd_run` resolves its own instance id via `_make_instance_id(loop_name)` (`cli/loop/runner.py:136`) at `cli/loop/run.py:199-203` when `args.foreground_internal` is unset — confirming a normal foreground run never receives an externally supplied id.
- `load_and_validate(..., raise_on_error=False)` (`fsm/validation/structural_rules.py:1873`, drifted from a stale `:1860` citation) still raises unconditionally on `FileNotFoundError` (line 1898), non-mapping YAML (line 1904), and missing required top-level fields (line 1924) — only post-parse structural/reachability validator output (`validate_fsm` plus four more passes — `_validate_with_bindings`, `_validate_loop_references`, `_validate_fragment_bindings`, `_validate_artifact_output_subloop_reachability` — lines 1964-1977, not "three more passes" at 1951-1957) is converted to a returned `(fsm, errors)` tuple instead of raising. **Correction:** the claim that "there is no existing precedent... for consuming that returned list" is wrong. `FSMExecutor._execute_sub_loop` (`executor.py:1116`) and `_validate_with_bindings` itself (`structural_rules.py:297`) do discard it (`child_fsm, _ = load_and_validate(...)`), but two call sites cited elsewhere in this same issue's own Integration Map — `cli/doctor.py:679` and `cli/logs.py:2349` — **do** consume the returned violations list (checking `any(v.severity == ERROR for v in violations)`). The new validation-response conversion has an established call-site pattern to follow after all.

## Implementation Steps

1. Implement/store-test approval eligibility and atomic request-key mapping; update queue status consumers and explicit per-entry host acceptance.
2. Prove the production queue path with watcher-running, concurrent-submit, cancellation, retry/revive, and per-entry acceptance tests before connecting the page.
3. Add lifecycle validation, immutable artifact persistence, workspace/issue binding, and structured child start metadata; test LOOP subprocess behavior with stubs.
4. Factor the builder renderer; add same-origin page/issue/request routes and method dispatch without changing existing GET/SSE behavior.
5. Wire review/submission/retry/readback UI and update docs/golden output. Port useful spike assertions to these production paths, then delete the old spike directory.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `awaiting_approval` status to `QUEUE_STATUSES` frozenset (`QUEUE_TERMINAL_STATUSES` unchanged — it is non-terminal)
- Add `awaiting_approval` color entry to `_STATUS_COLOR` dict in `cli/queue.py:51`
- Bump `SCHEMA_VERSION` to 4 and append the v4 migration (new nullable columns + partial unique index on `(workspace_id, request_id)`) to `_MIGRATIONS` in `queue_store.py:116-150`; extend `QueueEntry` dataclass, `to_dict`, `_from_row` (`queue_store.py:334-383`)
- Add `awaiting_approval` to `cancel_entry`'s SQL guard (`queue_store.py:625`) and `cmd_cancel`'s status list (`cli/queue.py:922`); add the approval-aware target status to `revive_entry` (`queue_store.py:634`, currently unguarded) and `reset_to_pending` (`queue_store.py:491`)
- Add `cwd=` to `_run_loop_entry`'s `Popen` (`cli/queue.py:411`) and the helper-thread/poll structure around `communicate()` for metadata observation
- `ll-queue list`/`status` output shows request id, issue id, and revision id for builder-origin rows
- Update hardcoded status vocabulary in `_tool_queue_list` MCP tool description (`mcp_server/tools.py:920-925`) and test assertion in `test_queue_store.py:446,454-455` (TestStatusVocabulary)
- Update `test_status_color_keys_match_queue_statuses` locked test in `test_cli_queue_run.py:1126-1132` once `_STATUS_COLOR` entry is added
- Wire `--id` and `--approve` flags into argparse at `cli/queue.py:main_queue()` lines 938,1042-1057
- Wire opt-in serve flag into argparse at `cli/artifact/serve.py:add_serve_parser()` line 37
- Add `_make_instance_id` reference in `mcp_server/tasks.py` if start-metadata contract changes (line 104,107)
- `test_loop_entry_input_passed_as_positional` and `test_loop_entry_intercepted_before_run_action` in `test_cli_queue_run.py` lines 384-395,340-357 exercise ordinary (non-builder-origin) entries and per Program Design § Start-metadata channel should NOT need updating once the LOOP subprocess metadata-file flag is added (see Tests section correction above) — verify this holds at implementation time rather than assuming breakage
- Port reusable assertions from `scripts/tests/spike/level2_run_handoff/test_level2_run_handoff.py`: `test_submit_creates_pending_record_not_auto_decided`, `test_duplicate_submit_returns_existing_record_without_retriggering`, `test_complete_rejects_binding_mismatch`, `test_submit_rejects_missing_binding_fields`, `test_ledger_persists_across_process_restart`, `test_observe_reflects_transitions_without_synchronous_decision_in_submit` into production test files (`test_queue_store.py`, `test_cli_queue_run.py`), then delete the spike directory
- Update `docs/reference/API.md` line 10997-11020 to add new function exports, line 11001-11002 inline comments for status changes, line 11444-11493 for SseBridge method-aware dispatch and security contract
- Update `docs/reference/CLI.md` lines 5062-5257, 912, 4394-4395 with `ll-queue run --id --approve` and new `ll-artifact serve` opt-in flag documentation
- Update `docs/ARCHITECTURE.md` lines 834-844 to add v4 schema-migration row (following ENH-3416 v3 precedent) and expand prose for `awaiting_approval` transitions
- Add level-2 render target row to `docs/reference/ARTIFACT_CONTROL_LEVELS.md` table (line 49-59) with policy-builder connected-builder declaration
- Update `docs/guides/POLICY_ROUTER_GUIDE.md` with cross-link to ARTIFACT_CONTROL_LEVELS.md per the **Binding now:** requirement (which lives in `ARTIFACT_CONTROL_LEVELS.md:61-63` itself, not in POLICY_ROUTER_GUIDE.md — see Documentation section correction above)
- Ensure new policy-revision validation caller catches pre-parse exceptions from `load_and_validate` without changing message format (pinned by existing docs/development/TESTING.md example line 295-298)

## Acceptance Criteria

- [ ] Submitting while a watcher runs produces `awaiting_approval` and zero subprocess dispatches. Generic drain, direct generic claim, requeue/revive, and restart cannot bypass approval. Existing ordinary pending jobs still execute.
- [ ] Reviving or requeueing a rejected/unapproved builder request (via CLI or MCP `queue_requeue`) returns it to `awaiting_approval`, not `pending`. An approved entry that hits a retryable failure or owner death returns to `pending` and is retried by a generic drainer without re-approval.
- [ ] Builder-origin LOOP dispatch runs with `cwd` equal to the persisted project root and no 120 s default timeout; ordinary LOOP entries keep today's exact argv and cwd behavior.
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
- `/ll:verify-issues` - 2026-09-18T01:26:23 - `eff5f7b6-7e2a-4e3b-9ab1-2c3de2810754.jsonl`
- manual review - 2026-09-17 - merged duplicate Program Design sections; pinned approval-durability/retry rules, v4 schema + partial unique index, `--id`/`--approve` semantics, LOOP cwd/timeout, metadata-channel thread/flag design, `write_bytes` persistence; clarified FEAT-3488 block as merge-ordering only
- `/ll:wire-issue` - 2026-09-17T06:29:23 - `cfe75f8a-6f82-4bce-bf08-9275049cd46d.jsonl`
- `/ll:reconcile-issue` - 2026-09-17T06:16:53 - `eb34f2f3-799f-4ff3-94f5-01cb135bc89a.jsonl`
- `/ll:refine-issue` - 2026-09-17T06:14:10 - `bdd11f79-301a-46b5-9233-83f283efd28d.jsonl`
- `/ll:format-issue` - 2026-09-17T06:04:13 - `673b8d7f-311f-49c5-91da-9f35cbc67a87.jsonl`
- `/ll:capture-issue` - 2026-09-17T06:00:15 - `673b8d7f-311f-49c5-91da-9f35cbc67a87.jsonl`
- manual review - 2026-09-17 - extracted FEAT-3488 Phase B with explicit queue approval, atomic request mapping, real LOOP identity, validation failures, project binding, and production-path verification
