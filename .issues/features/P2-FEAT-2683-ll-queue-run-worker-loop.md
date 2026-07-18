---
id: FEAT-2683
title: 'll-queue run: serial dequeue-and-execute worker loop'
type: FEAT
priority: P2
status: done
captured_at: '2026-07-18T00:00:00Z'
completed_at: '2026-07-18T22:19:54Z'
discovered_date: 2026-07-18
discovered_by: issue-size-review
parent: EPIC-2670
depends_on:
- FEAT-2682
relates_to:
- FEAT-2669
- FEAT-2682
labels:
- queue
- cli
- scheduling
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-2683: `ll-queue run` — serial dequeue-and-execute worker loop

## Summary

Add the `ll-queue run` worker that dequeues persisted entries (from
FEAT-2682's store) by priority/FIFO and dispatches each through
ENH-2668's shared `run_action()`, updating entry `status`/`result` with
the actual execution outcome. Strict serial execution for v1, per
FEAT-2669's resolved Q1.

## Parent Issue

Decomposed from FEAT-2669: Generic `ll-queue` (heterogeneous work-item
queue). This child covers the "execution-on-dequeue" half of FEAT-2669's
Expected Behavior — the half that turns persisted entries into actual
work getting done, replacing today's block-and-retry-lock pattern.

## Motivation

Today, nothing ever dequeues-and-executes a queue entry — a "queued"
FSM loop is just the blocked process retrying its lock
(`cli/loop/run.py:355-369`). FEAT-2682 gives entries a real home; this
child is what actually runs them.

## Current Behavior

Nothing ever dequeues-and-executes a persisted `ll-queue` entry.
FEAT-2682 gives entries a real sqlite-backed home (`.ll/queue.db`) with
`add`/`list`/`status`/`remove` commands, but entries sit in `pending`
forever — there is no worker that reads them out in priority/FIFO
order and dispatches them through `run_action()`. The only existing
"queued" concept is `cli/loop/run.py:355-369`'s block-and-retry-lock
pattern, which is a blocked process retrying its own lock acquisition,
not a dequeue-and-execute loop over persisted rows.

## Use Case

A user (or automation) enqueues a one-off skill/command invocation via
`ll-queue add`. They then run `ll-queue run` to drain the queue: each
pending entry is dispatched through `run_action()` in priority/FIFO
order, and `ll-queue status <id>` afterward reflects the real outcome
(success, failure, exit code, error) instead of a permanently-`pending`
row.

## Expected Behavior

- `ll-queue run` (or a long-running worker mode) dequeues entries from
  FEAT-2682's persistence layer in priority/FIFO order.
- Each entry's `ActionSpec` is dispatched through ENH-2668's
  `run_action()` (`runner_spec.py`), covering `SKILL`/`CMD`/`MCP`/
  `PROMPT` kinds. `RunnerType.LOOP` dispatch stays out of scope here —
  `run_action()` explicitly excludes it (raises `ValueError`); FSM loop
  execution remains on `PersistentExecutor` per ENH-2668's existing
  design, not something this child changes.
- Strict serial execution for v1 (FEAT-2669 Decision Rationale Q1) — a
  serial loop directly calling `run_action()`, no `ThreadPoolExecutor`/
  `WorkerPool`-style bounded concurrency. That precedent
  (`parallel/worker_pool.py`, `cli/sprint/run.py:487-498`) is
  issue-processing-specific and explicitly deferred as unneeded surface
  area for v1.
- On completion, the entry's `status` and `result` (per FEAT-2682's
  hybrid inline/scratch schema) reflect the actual execution outcome —
  not a liveness guess.

## Acceptance Criteria

- `ll-queue run` dequeues and executes entries through the ENH-2668
  runner in priority/FIFO order.
- Entry `status`/`result` reflect actual execution outcomes (success,
  failure, exit code, error) after `run` processes them.
- New test coverage for worker dequeue-and-dispatch ordering and
  status/result updates, independent of FEAT-2682's persistence tests.
- `python -m pytest scripts/tests/` exits 0.

## Impact

Without this worker, FEAT-2682's persistence layer is inert — entries
can be enqueued and inspected but never actually run, so `ll-queue`
provides no execution value over doing the work directly. This is the
child that turns the persisted queue into a working replacement for
the legacy block-and-retry-lock pattern.

## Scope Boundaries

- **In**: the dequeue loop, dispatch through `run_action()`, status/
  result write-back on completion.
- **Out**: queue persistence/schema and `add`/`list`/`status`/`remove`
  (FEAT-2682, a dependency of this child). Bounded-concurrency execution
  — explicitly deferred to a future issue if needed. `ll-loop run
  --queue` compat behavior (FEAT-2684).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/queue.py` — add a `cmd_run()` handler and register
  a `run` subparser in `main_queue()`, following the existing
  `cmd_add`/`cmd_list`/`cmd_status`/`cmd_remove` convention (each is a free
  function taking `args: argparse.Namespace) -> int`, imports its
  dependencies lazily inside the function body, and supports `--json` via
  `getattr(args, "json", False)`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` (~line 43) — the module docstring's
  usage banner hardcodes `- ll-queue: Persisted work-item queue: add/list/
  status/remove commands (FEAT-2682)`; not derived from argparse
  introspection, so it silently stays stale unless edited to mention `run`.
- `commands/help.md` (~line 303) — the `/ll:help` static listing has the same
  hardcoded `add/list/status/remove` enumeration for the `ll-queue` row.

### Dependent Files (Reused, Not Modified)
- `scripts/little_loops/runner_spec.py:run_action()` — the dispatch target.
  Signature: `run_action(spec: ActionSpec) -> RunnerResult`. Dispatches
  `SKILL`/`CMD`/`MCP`/`PROMPT` via an internal `_DISPATCH` table; `LOOP` (and
  `DSL`) are absent from that table and raise `ValueError` — confirms the
  Expected Behavior section's "explicitly excludes" claim.
  `RunnerResult` has no boolean success field — outcome must be derived from
  `exit_code: int`, `timed_out: bool`, and `error: str | None` (plus
  `stdout`/`stderr`).
- `scripts/little_loops/queue_store.py:list_entries()` — dequeue-order read,
  `ORDER BY priority ASC, enqueued_at ASC` (backed by index
  `idx_queue_entries_order`). No `WHERE status = 'pending'` clause exists yet
  — the worker must filter client-side or a future edit could add one.
- `scripts/little_loops/queue_store.py:update_entry_result(entry_id, status,
  result, db_path)` — status/result write-back call. Its docstring literally
  says "for the FEAT-2683 worker." Returns `bool` (`rowcount > 0`), not an
  exception, on a missing row. `status` is unconstrained free text; existing
  code (`cli/queue.py`'s `_STATUS_COLOR` dict) anticipates `pending`,
  `running`, `done`, `failed` as the display-relevant values, but only
  `pending` is written anywhere today.

### Similar Patterns
- `scripts/little_loops/issue_manager.py:AutoManager.run()` (and
  `_process_issue()`) — the closest existing "pop next, execute, record
  outcome" serial loop: `while not self._shutdown_requested:` → dequeue via
  `_get_next_issue()` → break on `None` → dispatch → map result to
  persistence via an `if/elif` chain — wrapped in `try/except Exception ->
  return 1` with a `finally:` cleanup block. `ll-queue run` should mirror this
  shape (loop until `list_entries()` yields no more `pending` rows, not a
  fixed count).
- `scripts/little_loops/cli/harness.py:_evaluate_and_report()` — shows how a
  `RunnerResult` is turned into a JSON-serializable outcome dict
  (`timed_out`/`error` checked first as immediate-failure paths, otherwise
  `exit_code` decides pass/fail). Use as the template for the `result` dict
  passed to `update_entry_result()`.
- `scripts/little_loops/cli/loop/run.py:355-427` — the legacy
  block-and-retry-lock pattern this worker replaces for the new persisted
  queue (kept for `--queue` FSM loops per FEAT-2684, out of scope here). Not
  a pattern to reuse — cited only because the Motivation section references
  it and an implementer should see why it doesn't apply to `ll-queue run`.

### Tests
- `scripts/tests/test_cli_queue.py` — direct sibling test file for
  `cli/queue.py`; shows the established test shape:
  `@pytest.fixture(autouse=True)` chdir to `tmp_path` (isolates
  `.ll/queue.db` per test since `DEFAULT_DB_PATH` is a relative path),
  `patch("sys.argv", [...])` + call `main_queue()` directly (no subprocess),
  assert via `capsys.readouterr()` + `json.loads(...)`.
- `scripts/tests/test_runner_spec.py` — reference for `RunnerType.LOOP`
  raising `ValueError` and the `RunnerResult` shape; the worker's dispatch
  tests should `patch` wherever `run_action` is imported into `cli/queue.py`
  and return a canned `RunnerResult`.
- `scripts/tests/test_queue_store.py` — existing FEAT-2682 persistence tests.
  Per this issue's Acceptance Criteria ("independent of FEAT-2682's
  persistence tests"), new dequeue/dispatch/write-back coverage should live
  in `test_cli_queue.py` (or a new `test_cli_queue_run.py`), not here.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_queue.py` — no existing test asserts on
  `main_queue()`'s subparser list or `--help` text, so adding a `run`
  subparser breaks nothing here. Add a `TestCmdRun` class following the
  `TestCmdAdd`/`TestCmdList` shape (autouse `_isolate_cwd` fixture,
  `patch("sys.argv", [...])`, call `main_queue()`, assert via `capsys`/
  `list_entries()`/`get_entry()`). Cover: dequeue-execute-record over
  pending entries, priority/FIFO dispatch order, empty-queue no-op exit,
  and status/result write-back for both success and failure outcomes.
- `scripts/tests/test_issue_manager.py:TestAutoManagerRun` (line ~2913,
  covers `AutoManager.run()`) — closest existing serial dequeue-execute-record
  loop test pattern to model `cmd_run()`'s tests after: mock the single
  per-item executor at its defining-module import site, assert on loop-exit
  counters/return code rather than side-channel output.
- Mock target for `run_action()`: `cli/queue.py` uses function-local imports
  everywhere (`cmd_add`/`_classify_action` import `runner_spec` symbols
  inside the function body, not at module level). Per this codebase's
  established convention (`test_runner_spec.py` patches
  `little_loops.runner_spec.resolve_host`/`call_mcp_tool`, not a
  `cli.harness`-aliased path), `cmd_run()`'s tests must patch
  `little_loops.runner_spec.run_action` (the defining module), not
  `little_loops.cli.queue.run_action`.

### Documentation
- `.claude/CLAUDE.md` — the root `ll-queue` CLI Tools entry currently lists
  only `add`/`list`/`status`/`remove`; will need a `run` mention once
  implemented.
- `docs/reference/API.md`, `docs/reference/CLI.md` — no existing `ll-queue
  run` documentation to update yet (command doesn't exist); add on
  implementation.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` (~lines 266, 312) — file-tree purpose comments
  (`# ll-queue persisted work-item queue CLI (FEAT-2682)`, `# Persisted
  ll-queue entry store (.ll/queue.db, FEAT-2682)`) tag FEAT-2682 only; a
  reader wouldn't know `run` (FEAT-2683) exists from this file — low urgency
  but worth a mention.
- `docs/reference/CONFIGURATION.md` (~line 822, "## Queue DB (ll-queue)") —
  narrative section on `.ll/queue.db` could note that `run` is the consumer
  that transitions entries out of `pending`.

### Configuration
- No new config keys identified — `scripts/little_loops/config/features.py`
  already defines `QueueConfig` (FEAT-2682) and
  `scripts/little_loops/queue_store.py:DEFAULT_DB_PATH = Path(".ll/queue.db")`
  is the fixed store location the worker reads/writes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `run_action()`'s return type (`RunnerResult`) has **no boolean
  success field** — the worker must derive `status`/outcome from
  `exit_code`/`timed_out`/`error`, following the same precedence
  `cli/harness.py:_evaluate_and_report()` uses (timeout/error checked before
  exit code).
- `list_entries()` has no `status` filter built in — it returns *all* rows in
  priority/FIFO order regardless of state. The worker's dequeue step must
  filter to `status == "pending"` itself (or a status filter param could be
  added to `queue_store.py`, which is currently out of this issue's declared
  scope since persistence changes belong to FEAT-2682).
- `update_entry_result()`'s docstring already names this issue
  ("for the FEAT-2683 worker"), confirming it's the intended write-back call
  — no new persistence function is needed.
- `_STATUS_COLOR` in `cli/queue.py` hardcodes exactly four status strings —
  `pending`/`running`/`done`/`failed` — and `cmd_list()`'s display path
  falls back to an uncolored default for anything outside that set.
  `cmd_run()`'s status writes must stay within this literal vocabulary
  (e.g. not `in_progress`/`executing`) to keep `cmd_list`'s coloring
  meaningful. `test_cli_queue.py:TestCmdRemove.test_remove_non_pending_requires_force`
  (line 213) already writes `"running"` by hand via `update_entry_result`,
  and `cmd_remove()`'s guard (`if entry.status != "pending"`, line ~209)
  hardcodes `"pending"` — `cmd_run()`'s client-side dequeue filter must
  compare against this exact same `"pending"` string literal.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| FEAT-2669 | Parent issue — full design context and resolved open questions |
| FEAT-2682 | Persistence layer this worker dequeues from |
| ENH-2668 | `run_action()` — the dispatch target for each dequeued entry |

## Session Log
- `/ll:manage-issue` - 2026-07-18T22:19:04 - `729f2d3c-c24f-4cfd-b375-adfbace65e12.jsonl`
- `/ll:ready-issue` - 2026-07-18T22:05:46 - `f1d91205-2082-46c8-b283-feeb4bf1226f.jsonl`
- `/ll:wire-issue` - 2026-07-18T22:02:15 - `51bcde63-d5e9-4cbe-ad70-5cf6213828e7.jsonl`
- `/ll:refine-issue` - 2026-07-18T21:56:38 - `cd7ea88a-5769-4264-856d-847a1a33c4a3.jsonl`
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `000582b3-d456-48ac-97b3-fcefbd8047d4.jsonl`

---

## Status

**Open** | Created: 2026-07-18 | Priority: P2
