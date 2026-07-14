---
id: FEAT-2619
type: FEAT
priority: P3
status: done
captured_at: 2026-07-12 19:49:49+00:00
completed_at: '2026-07-14T18:52:26Z'
discovered_date: 2026-07-12
discovered_by: scope-epic
parent: EPIC-2616
depends_on:
- ENH-2617
decision_needed: false
learning_tests_required:
- psutil
size: Very Large
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

_Wiring pass added by `/ll:wire-issue`:_
- `os.kill` mocking precedent — `scripts/tests/test_concurrency.py:193-233`
  (`test_stale_lock_eperm_treated_as_alive` / `test_stale_lock_esrch_treated_as_dead`)
  is the canonical idiom: `patch("os.kill", side_effect=OSError(errno.ESRCH, ...))`
  as a context manager, distinguishing ESRCH (dead) vs EPERM (alive). Follow this
  when asserting the SIGTERM target + identity gate in `TestQueueRemoveCommand`. For
  pure dead-PID cases needing no `os.kill` assertion, the `pid: 99999999` sentinel
  idiom (`test_cli_loop_queue.py:202-239`, `TestReadQueueEntries`) is simpler.
  [Agent 3 finding]
- Delete-and-assert-others fixture idiom — `TestReadQueueEntries.test_dead_pid_entries_are_pruned`
  (`test_cli_loop_queue.py:299-333`): each test builds its own `tmp_path/".queue"`
  inline, writes two `{uuid}.json` entries (target + survivor), captures the target
  `Path` handle before the call, then asserts `not target.exists()` alongside a
  positive assertion the survivor is untouched. Mirror this exactly in
  `TestQueueRemoveCommand`. [Agent 3 finding]
- **No test breakage** — no existing test enumerates the `queue` subcommand list or
  snapshots `ll-loop queue --help`; `test_queue_no_subcommand_prints_help`
  (`test_cli_loop_dispatch.py:1087`) asserts only `return == 1`. Adding `remove` is
  additive-only from the suite's perspective. [Agent 3 finding]
- `scripts/tests/test_wiring_cli_registry.py` — `DOC_STRINGS_PRESENT` (lines 146-148)
  pins doc-string needles for `ll-loop queue list` only; it will **not** fail when
  `remove` ships without docs (docs owned by ENH-2630), so it is not a gate for this
  issue — but it is the exact mechanism ENH-2630 must extend with parallel
  `queue remove` needles. FYI only; do not edit here. [Agent 2 finding]

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

> **Selected:** Option A (psutil identity verification) — the only option that
> satisfies the issue's own acceptance wording ("verify the tracked PID's
> identity, not just liveness"); guard psutil in try/except with a
> refuse-and-still-delete fallback since the codebase has no psutil precedent.

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

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-14.

**Selected**: Option A — psutil identity verification

**Reasoning**: Option B scores higher on raw codebase fit (it reuses the
widely-called `_process_alive` helper — 14+ call sites — and the existing
"check-liveness → signal/delete" idiom with zero new imports), but it directly
contradicts FEAT-2619's own Summary and Acceptance Criteria, which explicitly
require verifying the tracked PID's **identity, not just liveness**. Option A is
the only option that meets that binding constraint. `psutil>=5.9` is already a
declared dependency (`scripts/pyproject.toml:113`), so no new package is added —
only a first in-package import. The codebase has no psutil precedent (`host_guard.py`
deliberately shells out to `vm_stat`/`/proc/meminfo` instead), so the check must be
guarded in try/except (NoSuchProcess/AccessDenied) with a refuse-and-still-delete
fallback, and new test-mocking scaffolding for `psutil.Process` is expected.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — psutil identity | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |
| B — liveness-only | 3/3 | 3/3 | 3/3 | 1/3 | 10/12 |

**Key evidence**:
- Option A: `psutil` is declared but unused in `little_loops` runtime code (reuse
  score 0); `host_guard.py:1-7` explicitly avoids psutil for a similar
  process-inspection need. Higher-effort path, but the only one satisfying the AC.
- Option B: Reuses `_process_alive` (`fsm/concurrency.py:56-68`) and the stale-lock
  reaping idiom (`_helpers.py:193`) with zero new deps (reuse score 2) — but the
  issue's own research notes state it "does not actually satisfy the summary's 'not
  just liveness' wording," and it would require dropping the planned identity-gate
  test case.

**Note**: B is the higher-fit option and would be preferable if the AC were relaxed
to liveness-only. The selection honors the issue as currently scoped; if a maintainer
decides PID-recycling risk is acceptable, re-scope the AC and B becomes the winner.

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
- `/ll:manage-issue` - 2026-07-14T18:52:03Z - `f79c9a04-b051-43b9-95ec-546a2b44986d.jsonl`
- `/ll:ready-issue` - 2026-07-14T18:41:30 - `565cf34b-8a5f-4b9d-937b-76e57f098269.jsonl`
- `/ll:confidence-check` - 2026-07-14T00:00:00 - `14e1fc30-e29c-4918-a27d-edb58d9915e6.jsonl`
- `/ll:wire-issue` - 2026-07-14T18:25:04 - `08a60504-d18d-46d8-9c71-a478563b2ca9.jsonl`
- `/ll:decide-issue` - 2026-07-14T18:19:56 - `1137dcde-a149-4da9-8770-bce1682be284.jsonl`
- `/ll:refine-issue` - 2026-07-14T18:13:56 - `14902c7a-7cda-4d08-b928-c321adbfde4e.jsonl`
- `/ll:scope-epic` - 2026-07-12T19:49:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8999ce06-5d43-4dd5-bc03-841f57c28bf2.jsonl`
- `/ll:refine-issue` - 2026-07-13T19:15:00 - session JSONL unavailable
