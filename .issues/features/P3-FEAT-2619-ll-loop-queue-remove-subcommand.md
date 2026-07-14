---
id: FEAT-2619
type: FEAT
priority: P3
status: open
captured_at: 2026-07-12T19:49:49Z
discovered_date: 2026-07-12
discovered_by: scope-epic
parent: EPIC-2616
depends_on: [ENH-2617]
decision_needed: true
learning_tests_required: [psutil]
size: Very Large
---

# `ll-loop queue remove <id>` subcommand

## Summary

Add `ll-loop queue remove <id>` to cancel a queued waiter: verify the
tracked PID's identity (not just liveness) before signaling it, terminate
the waiting process, and delete its `.loops/.queue/<id>.json` entry. Must
not affect the currently-running (lock-holding) loop, only a waiter blocked
in `--queue`.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**The sibling `queue list` (FEAT-2618) is already implemented and merged**
(commit `0a755ba3`, status `done`). This makes FEAT-2619 an additive verb on an
existing, working nested subparser group — most of the scaffolding is done, and
this issue only adds the `remove` verb + a signal-and-delete function.

**The `queue` subparser group already exists** in
`scripts/little_loops/cli/loop/__init__.py`:
- Registration: `queue_parser` at lines 884-900 with
  `queue_subs = queue_parser.add_subparsers(dest="queue_command")` and a `list`
  verb. `"queue"` is already in `known_subcommands` (line 74).
- Dispatch: the `elif args.command == "queue":` branch at lines 955-959 currently
  routes only `queue_command == "list"` and otherwise prints help + returns 1.
- The module `scripts/little_loops/cli/loop/queue.py` already exists holding
  `cmd_queue_list()` — this issue adds `cmd_queue_remove()` alongside it (the
  module's docstring already anticipates the `remove` verb).

**Queue entry schema** (written at `run.py:357-369`, file `{uuid}.json`):
```json
{
  "id": "<uuid4>",
  "loopName": "<waiting loop name>",
  "enqueuedAt": "<ISO-8601 UTC>",
  "context": { "waitingFor": "<lock holder>", "scope": "<scope>", "pid": <int> }
}
```
Critically, `context.pid` is `os.getpid()` **of the waiting process itself**
(run.py:365) — the process blocked in the wait-retry loop at run.py:378-391, NOT
the lock holder. So signaling `context.pid` targets exactly the waiter and cannot
affect the running lock-holder (whose PID lives in a `.running/` lock file, a
different namespace). This satisfies the "must not affect the lock-holding loop"
requirement by construction.

**The shared read helper** — `read_queue_entries(queue_dir)` at
`scripts/little_loops/cli/loop/_helpers.py:172-200` (ENH-2617, `done`): returns
live entries sorted by `enqueuedAt`, pruning+unlinking dead-PID files. `remove`
should locate the target entry through this helper (or by direct
`{id}.json` path lookup) rather than re-globbing.

**PID liveness probe** — `_process_alive(pid)` at
`scripts/little_loops/fsm/concurrency.py:56-68` (`os.kill(pid, 0)`; ESRCH=dead,
EPERM/other=alive). Liveness ≠ identity: a recycled PID passes `_process_alive`
but may now belong to an unrelated process. **The summary explicitly requires
identity verification "not just liveness" before signaling** — see Open Questions.

**Identity-verification substrate** — `psutil>=5.9` is a declared dependency
(`scripts/pyproject.toml:113`), so `psutil.Process(pid).cmdline()` /
`.create_time()` are available to confirm the target PID is actually a queued
`ll-loop` waiter before sending a signal. The queue entry stores **only `pid`**
(no start-time / identity token), and the entry schema is frozen (out of scope
per ENH-2617/ENH-2620), so identity must be verified against the live process's
attributes, not a stored token.

**No existing signal-a-tracked-PID pattern in queue code.** Signal precedent
elsewhere uses `SIGTERM`/`SIGINT` (`issue_manager.py:1190-1191`,
`parallel/orchestrator.py:222-223`) and `os.killpg` for process groups
(`subprocess_utils.py:277`). The waiter registers an `atexit` cleanup
(`run.py:370`, `_cleanup_queue_entry`) that unlinks its own queue file on normal
exit — but `atexit` handlers do **not** run on a bare `SIGTERM`, so `remove` must
delete the `{id}.json` file itself regardless of whether the signal was delivered.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/queue.py` — add `cmd_queue_remove(args, loops_dir) -> int`
  next to `cmd_queue_list`. Reuses the existing `read_queue_entries` /
  `colorize` / `print_json` imports; add `_process_alive` (from
  `little_loops.fsm.concurrency`) and stdlib `os`/`signal` imports.
- `scripts/little_loops/cli/loop/__init__.py` —
  - Add a `remove` sub-parser under `queue_subs` (after line 900): a positional
    `id` argument, plus flags per the chosen identity approach (`--force`,
    `-j/--json`). Model on `queue_list_parser` (lines 891-900).
  - Extend the dispatch branch (lines 955-959) with
    `elif getattr(args, "queue_command", None) == "remove": return cmd_queue_remove(args, loops_dir)`.
  - Import `cmd_queue_remove` in the `cli_event_context` import block alongside
    `cmd_queue_list` (line 39).

### Dependent / Reused (do not modify)
- `read_queue_entries()` — `_helpers.py:172-200` (locate target entry).
- `_process_alive()` — `fsm/concurrency.py:56-68` (pre-signal liveness gate).
- `print_json()` / `colorize()` — `cli/output.py`.
- Entry-writer `run.py:357-370` — read-only reference for schema + `atexit` cleanup semantics.

### Similar Patterns
- `cmd_queue_list()` — `queue.py:12-47` (the sibling verb: `--json` early
  short-circuit, `getattr(args, "json", False)`, friendly human message; mirror
  its exit-code + output shape).
- Signal handling: `issue_manager.py:1190`, `parallel/orchestrator.py:222`
  (SIGTERM/SIGINT usage).

### Tests
- `scripts/tests/test_cli_loop_queue.py` — add `TestQueueRemoveCommand`: build a
  `.loops/.queue/{uuid}.json` fixture (reuse the `TestReadQueueEntries` idiom),
  then assert `cmd_queue_remove`: (1) deletes the target file, (2) leaves other
  entries untouched, (3) returns non-zero + friendly error for an unknown id,
  (4) does not signal / delete when the PID identity check fails (unless
  `--force`), (5) `--json` output shape. Use a self-PID or a
  guaranteed-dead PID (`99999999`, per the existing dead-PID convention) rather
  than signaling a real unrelated process; monkeypatch `os.kill` to assert the
  signal target + that it is gated on the identity check.
- `scripts/tests/test_cli_loop_dispatch.py` — extend `TestMainLoopQueueDispatch`
  (line 1055) and the `_mock_handlers` fixture (add `cmd_queue_remove` at
  line 50 alongside `cmd_queue_list`): a routing test
  (`ll-loop queue remove <id>` → `cmd_queue_remove`, model on
  `test_queue_list_routes_to_handler` line 1058) and id-forwarding assertion.

### Documentation
- Owned by ENH-2620 (docs for the whole `queue` family). No doc edits in this issue.

## Proposed Solution

Implement `cmd_queue_remove(args, loops_dir)`:

1. `queue_dir = loops_dir / ".queue"`; resolve the target by id. Accept the full
   uuid; optionally accept an 8-char short-id prefix (matching `queue list`'s
   display) with an ambiguity guard. If no entry matches → friendly error
   ("No queued entry with id '<id>'"), return 1 (`print_json` error object /
   `[]`-analog in `--json` mode).
2. Read the entry's `context.pid`.
3. **Verify PID identity** before signaling (the summary's core requirement) —
   see the two options below.
4. If the identity check passes and `_process_alive(pid)`: `os.kill(pid, SIGTERM)`
   to unblock the waiter (it exits its wait-retry loop and terminates).
   If the process is already dead, skip signaling.
5. **Always** `Path(queue_dir / f"{id}.json").unlink(missing_ok=True)` — the
   waiter's `atexit` cleanup does not fire on SIGTERM, so `remove` owns file
   deletion.
6. Report outcome (human + `--json`); return 0 on success.

### Codebase Research Findings — identity verification (decision point)

The queue entry stores only `pid`, and PIDs recycle, so a bare
`os.kill(pid, SIGTERM)` risks signaling an unrelated recycled process. Two
viable ways to satisfy "verify the tracked PID's identity, not just liveness":

**Option A**: **psutil cmdline verification.** Before signaling, load
`psutil.Process(pid)` and confirm the process is a live `ll-loop` invocation
(e.g. `"ll-loop"` / `little_loops.cli.loop` appears in `.cmdline()`, or the
`.create_time()` predates `enqueuedAt`). Refuse to signal (and print a warning,
still delete the file) if the check fails; a `--force` flag bypasses the check.
Strongest guarantee against PID-recycling mis-kills; adds a `psutil` runtime
dependency to this path (already a declared dep).

**Option B**: **liveness-only best-effort.** Signal whenever `_process_alive(pid)`
is true, accepting the (small) PID-recycling window, and rely on `--force`-free
simplicity. Cheaper and dependency-free, but does not actually satisfy the
summary's "not just liveness" wording.

**Recommended**: Option A — it is the only option that meets the issue's
explicit acceptance wording ("verify the tracked PID's identity (not just
liveness)"), and `psutil` is already a first-class dependency. Guard the psutil
lookup in try/except (NoSuchProcess/AccessDenied) and fall back to refusing the
signal (file still deleted) so a permission error never mis-kills.

## Implementation Steps

1. Add `cmd_queue_remove(args, loops_dir)` to
   `scripts/little_loops/cli/loop/queue.py` implementing the flow above
   (id resolution → identity check → `os.kill(SIGTERM)` → `unlink(missing_ok=True)`).
2. Register the `remove` sub-parser (positional `id`, `--force`, `-j/--json`) and
   dispatch branch in `scripts/little_loops/cli/loop/__init__.py`; import the new
   handler at line 39.
3. Add `TestQueueRemoveCommand` to `scripts/tests/test_cli_loop_queue.py`
   (delete-target, leave-others, unknown-id, identity-gate, `--force`, `--json`),
   monkeypatching `os.kill` to assert the signal target.
4. Extend `TestMainLoopQueueDispatch` + `_mock_handlers` in
   `scripts/tests/test_cli_loop_dispatch.py` for `queue remove` routing.
5. `python -m pytest scripts/tests/test_cli_loop_queue.py scripts/tests/test_cli_loop_dispatch.py -v`.

## Acceptance Criteria

- `ll-loop queue remove <id>` verifies the tracked PID's **identity** (not just
  liveness) before signaling, terminates the matching waiter (SIGTERM), and
  deletes its `.loops/.queue/<id>.json` entry.
- An unknown / already-gone id prints a friendly message and returns non-zero
  (or a clear `--json` error), without signaling anything.
- The currently-running lock-holding loop is never signaled — only the waiter's
  own `context.pid`.
- The `{id}.json` file is deleted even when the signal is not delivered (dead or
  identity-mismatched PID), so no orphan entry lingers.
- New CLI-level tests in `test_cli_loop_queue.py` and dispatch tests in
  `test_cli_loop_dispatch.py` cover success, unknown-id, identity-gate, and
  `--json` cases and pass under `python -m pytest scripts/tests/`.

## Open Questions

- **Identity verification approach** (Option A vs B above) — resolve via
  `/ll:decide-issue`. Recommendation: Option A (psutil cmdline/create-time check
  + `--force` bypass), the only option meeting the "not just liveness" wording.
- **Short-id acceptance**: accept 8-char prefixes (matching `queue list` display)
  or require the full uuid? Recommendation: accept both with an ambiguity guard
  for ergonomics; low-risk, can defer to full-uuid-only for v1 if simpler.
- **Signal choice**: `SIGTERM` (graceful, lets the waiter run any handlers) vs
  `SIGKILL`. Recommendation: `SIGTERM` — the waiter is blocked in a wait loop and
  `remove` deletes the file itself, so graceful is sufficient.

## Session Log
- `/ll:scope-epic` - 2026-07-12T19:49:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8999ce06-5d43-4dd5-bc03-841f57c28bf2.jsonl`
- `/ll:refine-issue` - 2026-07-13T19:15:00 - session JSONL unavailable
